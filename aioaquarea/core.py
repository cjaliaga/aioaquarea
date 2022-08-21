"""Aquarea Client foy asyncio."""
from __future__ import annotations

import asyncio
import functools
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp

from .const import (AQUAREA_SERVICE_BASE, AQUAREA_SERVICE_CONTRACT,
                    AQUAREA_SERVICE_DEVICES, AQUAREA_SERVICE_LOGIN)
from .data import (Device, DeviceInfo, DeviceStatus, DeviceZoneInfo,
                   DeviceZoneStatus, ExtendedOperationMode, FaultError,
                   OperationMode, OperationStatus, SensorMode, Tank,
                   TankStatus)
from .errors import (ApiError, AuthenticationError, AuthenticationErrorCodes,
                     InvalidData)


def auth_required(fn):
    """Decorator to require authentication and to refresh login if it's able to."""
    @functools.wraps(fn)
    async def _wrap(client, *args, **kwargs):
        if client.is_logged is False:
            client.logger.warning(
                f"{client}: User is not logged or session is too old"
            )
            await client.login()

        try:
            response = await fn(client, *args, **kwargs)
        except AuthenticationError as exception:
            client.logger.warning(
                f"{client}: Auth Error: {exception.error_code} - {exception.error_message}."
            )

            # If the error is invalid credentials, we don't want to retry the request.
            if exception.error_code == AuthenticationErrorCodes.INVALID_USERNAME_OR_PASSWORD:
                raise

            client.logger.warning(f"{client}: Trying to login again.")
            await client.login()
            response = await fn(client, *args, **kwargs)

        return response

    return _wrap


class Client:
    """Aquarea Client"""
  
    _HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "max-age=0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/74.0",
    }

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        logger: Optional[logging.Logger] = None,
    ):

        self._login_lock = asyncio.Lock()
        self._sess = session
        self._username = username
        self._password = password
        self._logger = logger or logging.getLogger("aioaquarea")
        self._token_expiration: Optional[datetime] = None
        self._last_login: datetime = datetime.min

    @property
    def username(self) -> str:
        """The username used to login"""
        return self._username

    @property
    def password(self) -> str:
        """Return the password"""
        return self._password

    @property
    def token_expiration(self) -> Optional[datetime]:
        """Return the expiration date of the token"""
        return self._token_expiration

    @property
    def is_logged(self) -> bool:
        """Return True if the user is logged in"""
        if not self._token_expiration:
            return False

        now = datetime.astimezone(datetime.utcnow(), tz=timezone.utc)
        return now < self._token_expiration

    @property
    def logger(self) -> logging.Logger:
        """Return the logger"""
        return self._logger

    async def request(
        self,
        method: str,
        url: str,
        referer: str = AQUAREA_SERVICE_BASE,
        throw_on_error=True,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a request to Aquarea and return the response"""

        headers = kwargs.get("headers", {})
        headers.update(self._HEADERS)
        headers["referer"] = referer
        kwargs["headers"] = headers

        resp = await self._sess.request(method, AQUAREA_SERVICE_BASE + url, **kwargs)

        # Aquarea returns a 200 even if the request failed, we need to check the message property to see if it's an error
        # Some errors just require to login again, so we raise a AuthenticationError in those known cases
        errors = [FaultError]
        if throw_on_error:
            errors = await self.look_for_errors(resp)
            # If we have errors, let's look for authentication errors
            for error in errors:
                if error.error_code in AuthenticationErrorCodes.values():
                    raise AuthenticationError(error.error_code, error.error_message)

                raise ApiError(error.error_code, error.error_message)

        return resp

    async def look_for_errors(
        self, response: aiohttp.ClientResponse
    ) -> list[FaultError]:
        """Look for errors in the response and return them as a list of FaultError objects"""
        if response.content_type != "application/json":
            return []

        data = await response.json()

        if not isinstance(data, dict):
            return []

        return [
            FaultError(error["errorMessage"], error["errorCode"])
            for error in data.get("message", {})
        ]

    async def login(self) -> None:
        """Login to Aquarea and stores a token in the session"""
        intent = datetime.now()
        await self._login_lock.acquire()
        try:
            if self._last_login > intent:
                return

            params = {
                "var.inputOmit": "false",
                "var.loginId": self.username,
                "var.password": self.password,
            }

            response: aiohttp.ClientResponse = await self.request(
                "POST",
                AQUAREA_SERVICE_LOGIN,
                referer=AQUAREA_SERVICE_BASE,
                data=urllib.parse.urlencode(params),
            )

            data = await response.json()

            if not isinstance(data, dict):
                raise InvalidData(data)

            self._token_expiration = datetime.strptime(
                data["accessToken"]["expires"], "%Y-%m-%dT%H:%M:%S%z"
            )

            self._logger.info(
                f"Login successful for {self.username}. Access Token Expiration: {self._token_expiration}"
            )

            self._last_login = datetime.now()

        finally:
            self._login_lock.release()

    @auth_required
    async def get_devices(self, include_long_id=False) -> List[DeviceInfo]:
        """Get list of devices and its configuration, without status."""
        response = await self.request("GET", AQUAREA_SERVICE_DEVICES)
        data = await response.json()

        if not isinstance(data, dict):
            raise InvalidData(data)

        devices: List[DeviceInfo] = []

        for record in data["device"]:
            zones: list[DeviceZoneInfo] = []

            for zone_record in record["configration"][0]["zoneInfo"]:
                zone = DeviceZoneInfo(
                    zone_record["zoneId"],
                    zone_record["zoneName"],
                    zone_record["zoneType"],
                    zone_record["coolMode"] == "enable",
                    SensorMode(zone_record["zoneSensor"]),
                    SensorMode(zone_record["heatSensor"]),
                    SensorMode(zone_record["coolSensor"]),
                )
                zones.append(zone)

            device_id = record["deviceGuid"]
            long_id = (
                await self.get_device_long_id(device_id) if include_long_id else ""
            )

            device = DeviceInfo(
                device_id,
                record["configration"][0]["a2wName"],
                long_id,
                OperationMode(record["configration"][0]["operationMode"]),
                record["configration"][0]["tankInfo"][0]["tank"] == "Yes",
                record["configration"][0]["firmVersion"],
                zones,
            )

            devices.append(device)

        return devices

    @auth_required
    async def get_device_long_id(self, device_id: str) -> str:
        """Retrives device long id to be used to retrive device status"""
        cookies = dict(selectedGwid=device_id)
        resp = await self.request(
            "POST",
            AQUAREA_SERVICE_CONTRACT,
            referer=AQUAREA_SERVICE_BASE,
            cookies=cookies,
        )
        return resp.cookies.get("selectedDeviceId").value

    @auth_required
    async def get_device_status(self, long_id: str) -> DeviceStatus:
        """Retrives device status"""
        response = await self.request(
            "GET", f"{AQUAREA_SERVICE_DEVICES}/{long_id}?var.deviceDirect=1"
        )
        data = await response.json()

        device = data.get("status")[0]

        device_status = DeviceStatus(
            long_id,
            OperationStatus(device.get("operationStatus")),
            OperationStatus(device.get("deiceStatus")),
            device.get("outdoorNow"),
            ExtendedOperationMode(device.get("operationMode")),
            [
                FaultError(fault_status["errorMessage"], fault_status["errorCode"])
                for fault_status in device.get("faultStatus", [])
            ],
            device.get("direction"),
            device.get("pumpDuty"),
            [
                TankStatus(
                    OperationStatus(tank_status["operationStatus"]),
                    tank_status["temparatureNow"],
                    tank_status["heatMax"],
                    tank_status["heatMin"],
                    tank_status["heatSet"],
                )
                for tank_status in device.get("tankStatus", [])
            ],
            [
                DeviceZoneStatus(
                    zone_status["zoneId"],
                    zone_status["temparatureNow"],
                    OperationStatus(zone_status["operationStatus"]),
                )
                for zone_status in device.get("zoneStatus", [])
            ],
        )

        return device_status

    @auth_required
    async def get_device(
        self, device_info: DeviceInfo | None = None, device_id: str | None = None
    ) -> Device:
        """Retrieves device"""
        if not device_info and not device_id:
            raise ValueError("Either device_info or device_id must be provided")

        if not device_info:
            devices = await self.get_devices(include_long_id=True)
            device_info = next(
                filter(lambda d: d.device_id == device_id, devices), None
            )

        return DeviceImpl(
            device_info, await self.get_device_status(device_info.long_id), self
        )

class TankImpl(Tank):
    """Tank implementation"""

    _client: Client

    def __init__(self, status: TankStatus, client: Client) -> None:
        super().__init__(status)
        self._client = client

class DeviceImpl(Device):
    """Device implementation able to auto-refresh using the Aquarea Client"""

    def __init__(self, info: DeviceInfo, status: DeviceStatus, client: Client) -> None:
        super().__init__(info, status)
        self._client = client

        if self.has_tank:
            self._tank = TankImpl(self._status.tank_status[0], self._client)

    async def refresh_data(self) -> None:
        self._status = await self._client.get_device_status(self._info.long_id)

        if self.has_tank:
            self._tank = TankImpl(self._status.tank_status[0], self._client)

        self.__build_zones__()
