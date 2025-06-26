"""Aquarea Client foy asyncio."""
from __future__ import annotations

import asyncio
import datetime as dt
import functools
import logging
import re
from typing import Optional
import urllib.parse
import html
import hashlib
import base64
import secrets
import string
import time
import json
from wsgiref import headers

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
    AQUAREA_SERVICE_AUTH0_CLIENT,
    AQUAREA_SERVICE_BASE,
    AQUAREA_SERVICE_CONSUMPTION,
    AQUAREA_SERVICE_CONTRACT,
    AQUAREA_SERVICE_DEMO_BASE,
    AQUAREA_SERVICE_DEVICES,
    AQUAREA_SERVICE_LOGIN,
    AQUAREA_SERVICE_AUTH_CLIENT_ID,
    AquareaEnvironment,
    REDIRECT_URI,
    AQUAREA_SERVICE_TOKEN,
    AQUAREA_SERVICE_ACC_LOGIN,
    APP_CLIENT_ID,
    AUTH_0_CLIENT,
    BASE_PATH_ACC,
    BASE_PATH_AUTH,
    AUTH_API_USER_AGENT,
    AUTH_BROWSER_USER_AGENT,
)
from .data import (
    Device,
    DeviceInfo,
    DeviceModeStatus,
    DeviceStatus,
    DeviceZoneInfo,
    DeviceZoneStatus,
    ExtendedOperationMode,
    FaultError,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    OperationMode,
    OperationStatus,
    PowerfulTime,
    QuietMode,
    SensorMode,
    SpecialStatus,
    Tank,
    TankStatus,
    UpdateOperationMode,
    ZoneSensor,
    ZoneTemperatureSetUpdate,
    StatusDataMode
)
from .errors import (
    ApiError,
    AuthenticationError,
    AuthenticationErrorCodes,
    DataNotAvailableError,
    InvalidData,
)
from .statistics import Consumption, ConsumptionType, DateType

_LOGGER = logging.getLogger(__name__)

# Placeholder for external dependencies, will need to be adapted or mocked
class PanasonicSettings:
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.scope = None
        self.clientId = None

    def set_token(self, access_token, refresh_token, expires_at, scope):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.scope = scope

class CCAppVersion:
    def __init__(self):
        self.version = "2.1.1" # Default version
    async def refresh(self):
        # In a real scenario, this would fetch the latest app version
        pass
    async def get(self):
        return self.version

class PanasonicRequestHeader:

    @staticmethod
    async def get(settings: PanasonicSettings, app_version: CCAppVersion, include_client_id = True):
        if settings.access_token is None:
            raise AuthenticationError(AuthenticationErrorCodes.API_ERROR, "Access token is missing from settings.")

        now = dt.datetime.now() # Use dt for datetime
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")    
        api_key = PanasonicRequestHeader._get_api_key(timestamp, settings.access_token)  
        _LOGGER.debug(f"Request Timestamp: {timestamp} key: {api_key}")
        headers={
                "accept": "application/json; charset=utf-8",
                "content-type": "application/json",
                "user-agent": "G-RAC",
                "x-app-name": "Comfort Cloud",
                "x-app-timestamp": timestamp,
                "x-app-type": "1",
                "x-app-version": await app_version.get(),
                "x-cfc-api-key": api_key,
                "x-user-authorization-v2": "Bearer " + settings.access_token
            }
        if (include_client_id and settings.clientId):
            headers["x-client-id"] = settings.clientId
        return headers
    
    @staticmethod
    def get_aqua_headers(content_type: str = "application/x-www-form-urlencoded", referer:str = "https://aquarea-smart.panasonic.com/"):
        headers={
                "Cache-Control": "max-age=0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "deflate, br",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": AUTH_BROWSER_USER_AGENT,
                "content-type": content_type,
                "referer": referer
            }
        return headers
        
    @staticmethod
    def _get_api_key(timestamp, token):
        try:
            date = dt.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S') # Use dt for datetime
            timestamp_ms = str(int(date.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)) # Use dt for datetime
            
            components = [
                'Comfort Cloud'.encode('utf-8'),
                '521325fb2dd486bf4831b47644317fca'.encode('utf-8'),
                timestamp_ms.encode('utf-8'),
                'Bearer '.encode('utf-8'),
                token.encode('utf-8')
            ]
                
            input_buffer = b''.join(components)
            hash_obj = hashlib.sha256()
            hash_obj.update(input_buffer)
            hash_str = hash_obj.hexdigest()
            
            result = hash_str[:9] + 'cfc' + hash_str[9:]
            return result
        except Exception as ex:
            _LOGGER.error("Failed to generate API key")

# Helper functions from the provided code
def generate_random_string(length: int) -> str:
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def get_querystring_parameter_from_header_entry_url(response: aiohttp.ClientResponse, header_entry, querystring_parameter):
    header_entry_value = response.headers[header_entry]
    parsed_url = urllib.parse.urlparse(header_entry_value)
    params = urllib.parse.parse_qs(parsed_url.query)
    return params.get(querystring_parameter, [None])[0]

async def check_response(response: aiohttp.ClientResponse, step_name: str, expected_status: int):
    if response.status != expected_status:
        response_text = await response.text()
        _LOGGER.error(f"Error in {step_name}: Expected status {expected_status}, got {response.status}. Response: {response_text}")
        raise AuthenticationError(AuthenticationErrorCodes.API_ERROR, f"Error in {step_name}: Unexpected status code {response.status}")

async def has_new_version_been_published(response: aiohttp.ClientResponse) -> bool:
    # This is a placeholder, in a real scenario this would check for new app versions
    return False

def auth_required(fn):
    """Decorator to require authentication and to refresh login if it's able to."""

    @functools.wraps(fn)
    async def _wrap(client, *args, **kwargs):
        if client.is_logged is False:
            client.logger.warning(f"{client}: User is not logged or session is too old")
            await client.login()

        try:
            response = await fn(client, *args, **kwargs)
        except AuthenticationError as exception:
            client.logger.warning(
                f"{client}: Auth Error: {exception.error_code} - {exception.error_message}."
            )

            # If the error is invalid credentials, we don't want to retry the request.
            if (
                exception.error_code
                == AuthenticationErrorCodes.INVALID_USERNAME_OR_PASSWORD
                or not client.is_refresh_login_enabled
            ):
                raise

            client.logger.warning(f"{client}: Trying to login again.")
            await client.login()
            response = await fn(client, *args, **kwargs)

        return response

    return _wrap


class Client:
    """Aquarea Client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        refresh_login: bool = True,
        logger: Optional[logging.Logger] = None,
        environment: AquareaEnvironment = AquareaEnvironment.PRODUCTION,
        device_direct: bool = True,
    ):
        """
        Initializes a new instance of the `Core` class.

        Args:
            session (aiohttp.ClientSession): The aiohttp client session.
            username (str, optional): The username for authentication. Defaults to None.
            password (str, optional): The password for authentication. Defaults to None.
            refresh_login (bool, optional): Whether to refresh the login. Defaults to True.
            logger (Optional[logging.Logger], optional): The logger instance. Defaults to None.
            environment (AquareaEnvironment, optional): The environment to use. Defaults to AquareaEnvironment.PRODUCTION.
            device_direct (bool, optional): Whether to use device direct mode. Defaults to True.

        Raises:
            ValueError: If the environment is set to PRODUCTION and username or password are not provided.
        """
        if environment == AquareaEnvironment.PRODUCTION and (
            not username or not password
        ):
            raise ValueError("Username and password must be provided")

        self._login_lock = asyncio.Lock()
        self._sess = session
        self._username = username
        self._password = password
        self._refresh_login = refresh_login
        self._logger = logger or logging.getLogger("aioaquarea")
        self._token_expiration: Optional[dt.datetime] = None
        self._last_login: dt.datetime = dt.datetime.min
        self._environment = environment
        self._base_url = (
            AQUAREA_SERVICE_BASE
            if environment == AquareaEnvironment.PRODUCTION
            else AQUAREA_SERVICE_DEMO_BASE
        )
        self._device_direct = (
            device_direct if environment == AquareaEnvironment.PRODUCTION else False
        )
        self._access_token: Optional[str] = None
        self._settings = PanasonicSettings()
        self._app_version = CCAppVersion()
        self._settings.username = username
        self._settings.password = password
        self._settings.access_token = self._access_token # Initialize with current access token if any
        self._settings.refresh_token = None # Will be set during authentication
        self._settings.expires_at = None # Will be set during authentication
        self._settings.scope = None # Will be set during authentication
        self._settings.clientId = None # Will be set during authentication

        self._groups = None
        self._devices: list[DeviceInfo] | None = None
        self._unknown_devices: list[DeviceInfo] = []
        self._cache_devices = {}
        self._device_indexer = {}

    @property
    def username(self) -> str:
        """The username used to login."""
        return self._username

    @property
    def password(self) -> str:
        """Return the password."""
        return self._password

    @property
    def is_refresh_login_enabled(self) -> bool:
        """Return True if the client is allowed to refresh the login."""
        return self._refresh_login

    @property
    def token_expiration(self) -> Optional[dt.datetime]:
        """Return the expiration date of the token."""
        return self._token_expiration

    @property
    def is_logged(self) -> bool:
        """Return True if the user is logged in."""
        if not self._access_token:
            return False

        # We don't have an expiration time, so we assume the token is valid
        if not self._token_expiration:
            return True
        
        now = dt.datetime.now(tz=dt.timezone.utc)
        return now < self._token_expiration

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
        return self._logger

    async def request(
        self,
        method: str,
        url: str = None,
        external_url: str = None,
        referer: str = AQUAREA_SERVICE_BASE,
        throw_on_error=True,
        content_type: str = "application/json", # Default to application/json
        headers: Optional[dict] = None, # New parameter for custom headers
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a request to Aquarea and return the response."""

        if headers is None:
            headers = await PanasonicRequestHeader.get(self._settings, self._app_version)
        
        request_headers = kwargs.get("headers", {})
        headers.update(request_headers)
        kwargs["headers"] = headers

        if external_url is not None:
            parsed_external_url = urllib.parse.urlparse(external_url)
            if not parsed_external_url.scheme or not parsed_external_url.netloc:
                # If external_url is a relative path, prepend the base URL
                url = self._base_url + external_url
            else:
                # If external_url is already a full URL, use it directly
                url = external_url
        else:
            url = self._base_url + url

        print(f"Requesting URL: {url} with method: {method} and headers: {headers}")
        resp = await self._sess.request(method, url, **kwargs)

        if resp.content_type == "application/json":
            data = await resp.json()

            # let's check for access token and expiration time
            if self._access_token and self.__contains_valid_token(data):
                self._access_token = data["accessToken"]["token"]
                self._token_expiration = dt.datetime.strptime(
                    data["accessToken"]["expires"], "%Y-%m-%dT%H:%M:%S%z"
                )

            # Aquarea returns a 200 even if the request failed, we need to check the message property to see if it's an error
            # Some errors just require to login again, so we raise a AuthenticationError in those known cases
            errors = [FaultError]
            if throw_on_error:
                errors = await self.look_for_errors(data)
                # If we have errors, let's look for authentication errors
                for error in errors:
                    if error.error_code in list(AuthenticationErrorCodes):
                        raise AuthenticationError(error.error_code, error.error_message)

                    raise ApiError(error.error_code, error.error_message)

        return resp

    def __contains_valid_token(self, data: dict) -> bool:
        """Check if the data contains a valid token."""
        return (
            "accessToken" in data
            and "token" in data["accessToken"]
            and "expires" in data["accessToken"]
        )

    async def look_for_errors(
        self, data: dict
    ) -> list[FaultError]:
        """Look for errors in the response and return them as a list of FaultError objects."""
        if not isinstance(data, dict):
            return []

        messages = data.get("message", [])
        if not isinstance(messages, list):
            messages = [messages] # Wrap single string message in a list

        fault_errors = []
        for error_item in messages:
            if isinstance(error_item, dict) and "errorMessage" in error_item and "errorCode" in error_item:
                fault_errors.append(FaultError(error_item["errorMessage"], error_item["errorCode"]))
            elif isinstance(error_item, str):
                fault_errors.append(FaultError(error_item, "unknown_error_code"))
        return fault_errors

    async def login(self) -> None:
        """Login to Aquarea and stores a token in the session."""
        intent = dt.datetime.now()
        await self._login_lock.acquire()
        try:
            if self._last_login > intent:
                return

            if self._environment is AquareaEnvironment.DEMO:
                await self.__login_demo()
            else:
                await self.authenticate(self._username, self._password)
                
            self._last_login = dt.datetime.now()
            self._access_token = self._settings.access_token
            self._token_expiration = dt.datetime.fromtimestamp(self._settings.expires_at, tz=dt.timezone.utc)
            await self._get_groups()
        finally:
            self._login_lock.release()

    async def _get_groups(self):
        self._groups = await self.request(
            "GET",
            external_url=f"{BASE_PATH_ACC}/device/group",
            headers=await PanasonicRequestHeader.get(self._settings, self._app_version)
        )
        self._groups = await self._groups.json()
        self._devices = None

    async def __login_demo(self) -> None:
        _ = await self.request("GET", "", referer=self._base_url)
        self._token_expiration = dt.datetime.astimezone(
            dt.datetime.utcnow(), tz=dt.timezone.utc
        ) + dt.timedelta(days=1)


    async def authenticate(self, username: str, password: str):
        self._sess.cookie_jar.clear_domain('authglb.digital.panasonic.com')
        # generate initial state and code_challenge
        code_verifier = generate_random_string(43)

        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(
                code_verifier.encode('utf-8')
            ).digest()).split('='.encode('utf-8'))[0].decode('utf-8')
        
        authorization_response = await self._authorize(code_challenge)
        authorization_redirect = authorization_response.headers['Location']
        
        # check if the user can skip the authentication workflows - in that case, 
        # the location is directly pointing to the redirect url with the "code"
        # query parameter included
        if authorization_redirect.startswith(REDIRECT_URI):
            code = get_querystring_parameter_from_header_entry_url(
                authorization_response, 'Location', 'code')
        else:
            code = await self._login(authorization_response, username, password)
        
        await self._request_new_token(code, code_verifier)
        await self._retrieve_client_acc()
        
    async def refresh_token(self):
        self._logger.debug("Refreshing token")
        # do before, so that timestamp is older rather than newer        
        now = dt.datetime.now()
        unix_time_token_received = time.mktime(now.timetuple())

        response = await self._sess.post(
            f'{BASE_PATH_AUTH}/oauth/token',
            headers={
                "Auth0-Client": AUTH_0_CLIENT,
                "user-agent": AUTH_API_USER_AGENT,
            },
            json={
                "scope": self._settings.scope,
                "client_id": APP_CLIENT_ID,
                "grant_type": "refresh_token"
            },
            allow_redirects=False)
        await check_response(response, 'refresh_token', 200)
        token_response = json.loads(await response.text())
        self._set_token(token_response, unix_time_token_received)


    async def _authorize(self, challenge) -> aiohttp.ClientResponse:
        # --------------------------------------------------------------------
        # AUTHORIZE
        # --------------------------------------------------------------------
        state = generate_random_string(20)
        self._logger.debug("Requesting authorization, %s", json.dumps({'challenge': challenge, 'state': state}))

        response = await self._sess.get(
            f'{BASE_PATH_AUTH}/authorize',
            headers={
                "user-agent": AUTH_API_USER_AGENT,
            },
            params={
                "scope": "openid offline_access comfortcloud.control a2w.control",
                "audience": f"https://digital.panasonic.com/{APP_CLIENT_ID}/api/v1/",
                "protocol": "oauth2",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "auth0Client": AUTH_0_CLIENT,
                "client_id": APP_CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "state": state,
            },
            allow_redirects=False)
        await check_response(response, 'authorize', 302)
        return response
        
        
    async def _login(self, authorization_response: aiohttp.ClientResponse, username, password):
        
        state = get_querystring_parameter_from_header_entry_url(
                authorization_response, 'Location', 'state')
        location = authorization_response.headers['Location']
        self._logger.debug("Following authorization redirect, %s", json.dumps({'url': f"{BASE_PATH_AUTH}/{location}", 'state': state}))
        response = await self._sess.get(
                f"{BASE_PATH_AUTH}/{location}",
                allow_redirects=False)
        await check_response(response, 'authorize_redirect', 200)

        # get the "_csrf" cookie
        csrf_cookie = response.cookies['_csrf']
        
        # -------------------------------------------------------------------
        # LOGIN
        # -------------------------------------------------------------------
        self._logger.debug("Authenticating with username and password, %s", json.dumps({'csrf':csrf_cookie,'state':state}))
        response = await self._sess.post(
            f'{BASE_PATH_AUTH}/usernamepassword/login',
            headers={
                "Auth0-Client": AUTH_0_CLIENT,
                "user-agent": AUTH_API_USER_AGENT,
            },
            json={
                "client_id": APP_CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "tenant": "pdpauthglb-a1",
                "response_type": "code",
                "scope": "openid offline_access comfortcloud.control a2w.control",
                "audience": f"https://digital.panasonic.com/{APP_CLIENT_ID}/api/v1/",
                "_csrf": csrf_cookie,
                "state": state,
                "_intstate": "deprecated",
                "username": username,
                "password": password,
                "lang": "en",
                "connection": "PanasonicID-Authentication"
            },
            allow_redirects=False)
        await check_response(response, 'login', 200)

        # -------------------------------------------------------------------
        # CALLBACK
        # -------------------------------------------------------------------

        # get wa, wresult, wctx from body
        response_text = await response.text()
        self._logger.debug("Authentication response, %s", json.dumps({'html':response_text}))
        soup = BeautifulSoup(response_text, "html.parser")
        input_lines = soup.find_all("input", {"type": "hidden"})
        parameters = dict()
        for input_line in input_lines:
            parameters[input_line.get("name")] = input_line.get("value")

        self._logger.debug("Callback with parameters, %s", json.dumps(parameters))
        response = await self._sess.post(
            url=f"{BASE_PATH_AUTH}/login/callback",
            data=parameters,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": AUTH_BROWSER_USER_AGENT,
            },
            allow_redirects=False)
        await check_response(response, 'login_callback', 302)

        # ------------------------------------------------------------------
        # FOLLOW REDIRECT
        # ------------------------------------------------------------------

        location = response.headers['Location']
        self._logger.debug("Callback response, %s", json.dumps({'redirect':location, 'html': await response.text()}))

        response = await self._sess.get(
            f"{BASE_PATH_AUTH}/{location}",
            allow_redirects=False)
        await check_response(response, 'login_redirect', 302)
        location = response.headers['Location']
        self._logger.debug("Callback redirect, %s", json.dumps({'redirect':location, 'html': await response.text()}))

        return get_querystring_parameter_from_header_entry_url(
                response, 'Location', 'code')
    
    async def _request_new_token(self, code, code_verifier):
        self._logger.debug("Requesting a new token")
        # do before, so that timestamp is older rather than newer
        now = dt.datetime.now()
        unix_time_token_received = time.mktime(now.timetuple())

        response = await self._sess.post(
            f'{BASE_PATH_AUTH}/oauth/token',
            headers={
                "Auth0-Client": AUTH_0_CLIENT,
                "user-agent": AUTH_API_USER_AGENT,
            },
            json={
                "scope": "openid",
                "client_id": APP_CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier
            },
            allow_redirects=False)
        await check_response(response, 'get_token', 200)

        token_response = json.loads(await response.text())
        self._set_token(token_response, unix_time_token_received)
        
    def _set_token(self, token_response, unix_time_token_received):
        self._settings.set_token(
            token_response["access_token"], 
            token_response["refresh_token"],
            unix_time_token_received + token_response["expires_in"],
            token_response["scope"])
        
    async def _retrieve_client_acc(self):
        # ------------------------------------------------------------------
        # RETRIEVE ACC_CLIENT_ID
        # ------------------------------------------------------------------
        headers= await PanasonicRequestHeader.get(self._settings, self._app_version, include_client_id= False)
      
        response = await self._sess.post(
            f'{BASE_PATH_ACC}/auth/v2/login',
            headers = headers,
            json={
                "language": 0
            })
        if await has_new_version_been_published(response):
            self._logger.info("New version of acc client id has been published")
            await self._app_version.refresh()
            response = await self._sess.post(
                f'{BASE_PATH_ACC}/auth/v2/login',
                headers = await PanasonicRequestHeader.get(self._settings, self._app_version, include_client_id= False),
                json={
                    "language": 0
                })


        await check_response(response, 'get_acc_client_id', 200)

        json_body = json.loads(await response.text())
        self._settings.clientId = json_body["clientId"]
        return

    @auth_required
    async def get_devices(self) -> list[DeviceInfo]:
        """Get list of devices and its configuration, without status."""
        if self._devices is None:
            self._devices = []
            self._unknown_devices = []
            if self._groups is not None and 'groupList' in self._groups:
                for group in self._groups['groupList']:
                    device_list = group.get('deviceList', [])
                    if not device_list:
                        device_list = group.get('deviceIdList', [])

                    for device_raw in device_list:
                        if device_raw:
                            device_id = device_raw.get("deviceGuid")
                            device_name = device_raw.get("deviceName", "Unknown Device")
                            operation_mode = OperationMode(device_raw.get("operationMode", 0)) # Default to 0 if not found
                            has_tank = "tankStatus" in device_raw # Check for presence of tankStatus key
                            firmware_version = "Unknown" # Mock data as it's not in the new structure

                            zones: list[DeviceZoneInfo] = []
                            for zone_record in device_raw.get("zoneStatus", []):
                                # Mock data for fields not present in the new zoneStatus structure
                                zone_id = zone_record.get("zoneId")
                                if zone_id is not None:
                                    zone = DeviceZoneInfo(
                                        zone_id,
                                        f"Zone {zone_id}", # Mock zone name
                                        "Unknown", # Mock zone type
                                        False, # Mock cool_mode
                                        SensorMode.DIRECT, # Mock heat_sensor
                                        SensorMode.DIRECT, # Mock cool_sensor
                                        SensorMode.DIRECT, # Mock cool_sensor
                                    )
                                    zones.append(zone)

                            device_info = DeviceInfo(
                                device_id,
                                device_name,
                                device_id,
                                operation_mode,
                                has_tank,
                                firmware_version,
                                zones,
                                0
                            )
                            self._device_indexer[device_id] = device_id
                            self._devices.append(device_info)
        return self._devices + self._unknown_devices

    @auth_required
    async def get_device_status(self, device_info: DeviceInfo) -> DeviceStatus:
        """Retrives device status."""
        json_response = None
        if (device_info.status_data_mode == StatusDataMode.LIVE 
            or (device_info.device_id in self._cache_devices and self._cache_devices[device_info.device_id] <= 0)):
            try:
                payload = {
                    "apiName": f"/remote/v1/api/devices?gwid={device_info.device_id}&deviceDirect=1",
                    "requestMethod": "GET"
                }
                response = await self.request( # Use self.request
                    "POST", # Method is POST for the transfer API
                    url="remote/v1/app/common/transfer", # Specific URL for transfer API
                    json=payload, # Pass payload as json
                    throw_on_error=True
                )
                json_response = await response.json() # Get JSON from response
                device_info.status_data_mode = StatusDataMode.LIVE
            except Exception as e:
                _LOGGER.warning("Failed to get live status for device {} switching to cached data.".format(device_info.device_id))
                device_info.status_data_mode = StatusDataMode.CACHED
                self._cache_devices[device_info.device_id] = 10
        
        if json_response is None: # If live data failed or not requested, try cached
            payload = {
                "apiName": f"/remote/v1/api/devices?gwid={device_info.device_id}&deviceDirect=0",
                "requestMethod": "GET"
            }
            response = await self.request( # Use self.request
                "POST", # Method is POST for the transfer API
                url="remote/v1/app/common/transfer", # Specific URL for transfer API
                json=payload, # Pass payload as json
                throw_on_error=True
            )
            json_response = await response.json() # Get JSON from response
            print(f"Cached response for device {device_info.device_id}: {json_response}")
            #self._cache_devices[device_info.device_id] -= 1

        device = json_response.get("status")
        operation_mode_value = device.get("operationMode")

        device_status = DeviceStatus(
            long_id=device_info.device_id, # Use device_info.long_id here
            operation_status=OperationStatus(device.get("specialStatus")),
            device_status=DeviceModeStatus(device.get("deiceStatus")),
            temperature_outdoor=device.get("outdoorNow"),
            operation_mode=ExtendedOperationMode.OFF
            if operation_mode_value == 99
            else ExtendedOperationMode(operation_mode_value),
            fault_status=[
                FaultError(fault_status["errorMessage"], fault_status["errorCode"])
                for fault_status in device.get("faultStatus", [])
            ],
            direction=device.get("direction"),
            pump_duty=device.get("pumpDuty"),
            tank_status=[
                TankStatus(
                    OperationStatus(tank_status["operationStatus"]),
                    tank_status["temparatureNow"],
                    tank_status["heatMax"],
                    tank_status["heatMin"],
                    tank_status["heatSet"],
                )
                for tank_status in device.get("tankStatus", [])
                if isinstance(tank_status, dict)
            ],
            zones=[
                DeviceZoneStatus(
                    zone_id=zone_status.get("zoneId"),
                    temperature=zone_status.get("temparatureNow"),
                    operation_status=OperationStatus(zone_status.get("operationStatus")),
                    heat_max=zone_status.get("heatMax"),
                    heat_min=zone_status.get("heatMin"),
                    heat_set=zone_status.get("heatSet"),
                    cool_max=zone_status.get("coolMax"),
                    cool_min=zone_status.get("coolMin"),
                    cool_set=zone_status.get("coolSet"),
                    comfort_cool=zone_status.get("comfortCool"),
                    comfort_heat=zone_status.get("comfortHeat"),
                    eco_cool=zone_status.get("ecoCool"),
                    eco_heat=zone_status.get("ecoHeat"),
                )
                for zone_status in device.get("zoneStatus", [])
                if isinstance(zone_status, dict)
            ],
            quiet_mode=QuietMode(device.get("quietMode", 0)),
            force_dhw=ForceDHW(device.get("forceDHW", 0)),
            force_heater=ForceHeater(device.get("forceHeater", 0)),
            holiday_timer=HolidayTimer(device.get("holidayTimer", 0)),
            powerful_time=PowerfulTime(device.get("powerful", 0)),
            special_status=None, # Simplified to None
        )

        return device_status

    @auth_required
    async def get_device(
        self,
        device_info: DeviceInfo | None = None,
        device_id: str | None = None,
        consumption_refresh_interval: Optional[dt.timedelta] = None,
        timezone: dt.timezone = dt.timezone.utc,
    ) -> Device:
        """Retrieve device."""
        if not device_info and not device_id:
            raise ValueError("Either device_info or device_id must be provided")

        if not device_info:
            devices = await self.get_devices()
            device_info = next(
                filter(lambda d: d.device_id == device_id, devices), None
            )

        return DeviceImpl(
            device_info,
            await self.get_device_status(device_info),
            self,
            consumption_refresh_interval,
            timezone,
        )

    @auth_required
    async def post_device_operation_status(
        self, long_device_id: str, new_operation_status: OperationStatus
    ) -> None:
        """Post device operation status."""
        data = {
            "status": [
                {
                    "deviceGuid": long_device_id,
                    "operationStatus": new_operation_status.value,
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_device_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

        return None

    @auth_required
    async def post_device_tank_temperature(
        self, long_device_id: str, new_temperature: int
    ) -> None:
        """Post device tank temperature."""
        data = {
            "status": [
                {
                    "deviceGuid": long_device_id,
                    "tankStatus": [
                        {
                            "heatSet": new_temperature,
                        }
                    ],
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_tank_operation_status(
        self,
        long_device_id: str,
        new_operation_status: OperationStatus,
        new_device_operation_status: OperationStatus = OperationStatus.ON,
    ) -> None:
        """Post device tank operation status."""
        data = {
            "status": [
                {
                    "deviceGuid": long_device_id,
                    "operationStatus": new_device_operation_status.value,
                    "tankStatus": [
                        {
                            "operationStatus": new_operation_status.value,
                        }
                    ],
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_device_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_operation_update(
        self,
        long_id: str,
        mode: UpdateOperationMode,
        zones: dict[int, OperationStatus],
        operation_status: OperationStatus,
    ) -> None:
        """Post device operation update."""
        data = {
            "status": [
                {
                    "deviceGuid": long_id,
                    "operationMode": mode.value,
                    "operationStatus": operation_status.value,
                    "zoneStatus": [
                        {
                            "zoneId": zone_id,
                            "operationStatus": zones[zone_id].value,
                        }
                        for zone_id in zones
                    ],
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_set_special_status(
        self,
        long_id: str,
        special_status: SpecialStatus | None,
        zones: list[ZoneTemperatureSetUpdate],
    ) -> None:
        """Post device operation update."""
        data = {
            "status": [
                {
                    "deviceGuid": long_id,
                    "specialStatus": special_status.value if special_status else 0,
                    "zoneStatus": [
                        {
                            "zoneId": zone.zone_id,
                            "heatSet": zone.heat_set,
                            **(
                                {"coolSet": zone.cool_set}
                                if zone.cool_set is not None
                                else {}
                            ),
                        }
                        for zone in zones
                    ],
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    async def post_device_zone_heat_temperature(
        self, long_id: str, zone_id: int, temperature: int
    ) -> None:
        """Post device zone heat temperature."""
        return await self._post_device_zone_temperature(
            long_id, zone_id, temperature, "heatSet"
        )

    async def post_device_zone_cool_temperature(
        self, long_id: str, zone_id: int, temperature: int
    ) -> None:
        """Post device zone cool temperature."""
        return await self._post_device_zone_temperature(
            long_id, zone_id, temperature, "coolSet"
        )

    @auth_required
    async def _post_device_zone_temperature(
        self, long_id: str, zone_id: int, temperature: int, key: str
    ) -> None:
        """Post device zone temperature."""
        data = {
            "status": [
                {
                    "deviceGuid": long_id,
                    "zoneStatus": [
                        {
                            "zoneId": zone_id,
                            key: temperature,
                        }
                    ],
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_set_quiet_mode(self, long_id: str, mode: QuietMode) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "quietMode": mode.value}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_force_dhw(self, long_id: str, force_dhw: ForceDHW) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "forceDHW": force_dhw.value}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_force_heater(
        self, long_id: str, force_heater: ForceHeater
    ) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "forceHeater": force_heater.value}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_holiday_timer(
        self, long_id: str, holiday_timer: HolidayTimer
    ) -> None:
        """Post quiet mode."""
        data = {
            "status": [{"deviceGuid": long_id, "holidayTimer": holiday_timer.value}]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_request_defrost(self, long_id: str) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "forcedefrost": 1}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    @auth_required
    async def post_device_set_powerful_time(
        self, long_id: str, powerful_time: PowerfulTime
    ) -> None:
        """Post powerful time."""
        data = {
            "status": [
                {
                    "deviceGuid": long_id,
                    "powerfulRequest": powerful_time.value,
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
            json=data,
        )

    async def get_device_consumption(
        self, long_id: str, aggregation: DateType, date_input: str
    ) -> Consumption:
        """Get device consumption."""
        response = await self.request(
            "GET",
            f"{AQUAREA_SERVICE_CONSUMPTION}/{long_id}?{aggregation}={date_input}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}"
            ),
        )

        date_data = await response.json()
        return Consumption(date_data.get("dateData")[0])


class TankImpl(Tank):
    """Tank implementation."""

    _client: Client

    def __init__(self, status: TankStatus, device: Device, client: Client) -> None:
        super().__init__(status, device)
        self._client = client

    async def __set_target_temperature__(self, value: int) -> None:
        await self._client.post_device_tank_temperature(self._device.long_id, value)

    async def __set_operation_status__(
        self, status: OperationStatus, device_status: OperationStatus
    ) -> None:
        await self._client.post_device_tank_operation_status(
            self._device.long_id, status, device_status
        )


class DeviceImpl(Device):
    """Device implementation able to auto-refresh using the Aquarea Client."""

    def __init__(
        self,
        info: DeviceInfo,
        status: DeviceStatus,
        client: Client,
        consumption_refresh_interval: Optional[dt.timedelta] = None,
        timezone: dt.timezone = dt.timezone.utc,
    ) -> None:
        super().__init__(info, status)
        self._client = client
        self._timezone = timezone
        self._last_consumption_refresh: dt.datetime | None = None
        self._consumption_refresh_lock = asyncio.Lock()
        self._consumption_refresh_interval = consumption_refresh_interval

        if self.has_tank and self._status.tank_status:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

    async def refresh_data(self) -> None:
        self._status = await self._client.get_device_status(self._info.long_id)

        if self.has_tank:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

        self.__build_zones__()

        if self._consumption:
            await self.__refresh_consumption__()

    async def __refresh_consumption__(self) -> None:
        """Refreshes the consumption data."""
        if not self._consumption:
            return

        if self._consumption_refresh_lock.locked():
            return

        await self._consumption_refresh_lock.acquire()

        try:
            if (
                self._consumption_refresh_interval is not None
                and self._last_consumption_refresh is not None
                and dt.datetime.now(self._timezone) - self._last_consumption_refresh
                < self._consumption_refresh_interval
                and None not in self._consumption.values()
            ):
                return

            now = dt.datetime.now(self._timezone)
            for date in self._consumption:
                if (
                    now - date > dt.timedelta(days=2)
                    and self._consumption.get(date) is not None
                ):
                    continue

                self._consumption[date] = await self._client.get_device_consumption(
                    self.long_id, DateType.DAY, date.strftime("%Y-%m-%d")
                )

            self._last_consumption_refresh = dt.datetime.now(self._timezone)
        finally:
            self._consumption_refresh_lock.release()

    async def __set_operation_status__(self, status: OperationStatus) -> None:
        await self._client.post_device_operation_status(self.long_id, status)

    async def set_mode(
        self, mode: UpdateOperationMode, zone_id: int | None = None
    ) -> None:
        zones: dict[int, OperationStatus] = {}

        for zone in self.zones.values():
            if zone_id is None or zone.zone_id == zone_id:
                zones[zone.zone_id] = (
                    OperationStatus.OFF
                    if mode == UpdateOperationMode.OFF
                    else OperationStatus.ON
                )
            else:
                zones[zone.zone_id] = zone.operation_status

        tank_off = (
            not self.has_tank
            or self.has_tank
            and self.tank.operation_status == OperationStatus.OFF
        )

        operation_status = (
            OperationStatus.OFF
            if mode == UpdateOperationMode.OFF
            and tank_off
            and all(status == OperationStatus.OFF for status in zones.values())
            else OperationStatus.ON
        )

        await self._client.post_device_operation_update(
            self.long_id, mode, zones, operation_status
        )

    async def set_temperature(
        self, temperature: int, zone_id: int | None = None
    ) -> None:
        if not self.zones.get(zone_id).supports_set_temperature:
            return

        if self.mode in [ExtendedOperationMode.AUTO_COOL, ExtendedOperationMode.COOL]:
            await self._client.post_device_zone_cool_temperature(
                self.long_id, zone_id, temperature
            )
        elif self.mode in [ExtendedOperationMode.AUTO_HEAT, ExtendedOperationMode.HEAT]:
            await self._client.post_device_zone_heat_temperature(
                self.long_id, zone_id, temperature
            )

    async def set_quiet_mode(self, mode: QuietMode) -> None:
        await self._client.post_device_set_quiet_mode(self.long_id, mode)

    async def get_and_refresh_consumption(
        self, date: dt.datetime, consumption_type: ConsumptionType
    ) -> float | None:
        """Retrieve consumption data and asyncronously refreshes if necessary for the specified date and type.

        :param date: The date to get the consumption for
        :param consumption_type: The consumption type to get.
        """

        day = date.replace(hour=0, minute=0, second=0, microsecond=0)

        self._consumption[day] = await self._client.get_device_consumption(
            self.long_id, DateType.DAY, date.strftime("%Y-%m-%d")
        )

        return self._consumption[day].energy.get(consumption_type)[date.hour]

    def get_or_schedule_consumption(
        self, date: dt.datetime, consumption_type: ConsumptionType
    ) -> float | None:
        """Gets available consumption data or schedules retrieval for the next refresh cycle.
        :param date: The date to get the consumption for
        :param consumption_type: The consumption type to get
        """

        day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        consumption = self._consumption.get(day, None)

        if consumption is None:
            self._consumption[day] = None
            raise DataNotAvailableError(f"Consumption for {day} is not yet available")

        return consumption.energy.get(consumption_type)[date.hour]

    async def set_force_dhw(self, force_dhw: ForceDHW) -> None:
        """Set the force dhw.

        :param force_dhw: Set the Force DHW mode if the device has a tank.
        """
        if not self.has_tank:
            return

        await self._client.post_device_force_dhw(self.long_id, force_dhw)

    async def set_force_heater(self, force_heater: ForceHeater) -> None:
        """Set the force heater configuration.

        :param force_heater: The force heater mode.
        """
        if self.force_heater is not force_heater:
            await self._client.post_device_force_heater(self.long_id, force_heater)

    async def request_defrost(self) -> None:
        """Request defrost."""
        if self.device_mode_status is not DeviceModeStatus.DEFROST:
            await self._client.post_device_request_defrost(self.long_id)

    async def set_holiday_timer(self, holiday_timer: HolidayTimer) -> None:
        """Enable or disable the holiday timer mode.

        :param holiday_timer: The holiday timer option
        """
        if self.holiday_timer is not holiday_timer:
            await self._client.post_device_holiday_timer(self.long_id, holiday_timer)

    async def set_powerful_time(self, powerful_time: PowerfulTime) -> None:
        """Set the powerful time.

        :param powerful_time: Time to enable powerful mode
        """
        if self.powerful_time is not powerful_time:
            await self._client.post_device_set_powerful_time(
                self.long_id, powerful_time
            )

    async def __set_special_status__(
        self,
        special_status: SpecialStatus | None,
        zones: list[ZoneTemperatureSetUpdate],
    ) -> None:
        """Set the special status.
        :param special_status: Special status to set
        :param zones: Zones to set the special status for
        """
        await self._client.post_device_set_special_status(
            self.long_id, special_status, zones
        )
