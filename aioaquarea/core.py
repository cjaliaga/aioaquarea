"""Aquarea Client foy asyncio."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import functools
import logging
from typing import List, Optional
import urllib.parse

import aiohttp

from .const import (
    AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
    AQUAREA_SERVICE_BASE,
    AQUAREA_SERVICE_CONSUMPTION,
    AQUAREA_SERVICE_CONTRACT,
    AQUAREA_SERVICE_DEVICES,
    AQUAREA_SERVICE_LOGIN,
)
from .data import (
    Device,
    DeviceInfo,
    DeviceStatus,
    DeviceZoneInfo,
    DeviceZoneStatus,
    ExtendedOperationMode,
    FaultError,
    OperationMode,
    OperationStatus,
    QuietMode,
    SensorMode,
    Tank,
    TankStatus,
    UpdateOperationMode,
    ZoneSensor,
)
from .errors import ApiError, AuthenticationError, AuthenticationErrorCodes, InvalidData
from .statistics import Consumption, DateType


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
    """Aquarea Client"""

    _HEADERS = {
        # "Content-Type": "application/x-www-form-urlencoded",
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
        refresh_login: bool = True,
        logger: Optional[logging.Logger] = None,
    ):

        self._login_lock = asyncio.Lock()
        self._sess = session
        self._username = username
        self._password = password
        self._refresh_login = refresh_login
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
    def is_refresh_login_enabled(self) -> bool:
        """Return True if the client is allowed to refresh the login"""
        return self._refresh_login

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
        content_type: str = "application/x-www-form-urlencoded",
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a request to Aquarea and return the response"""

        headers = self._HEADERS.copy()
        request_headers = kwargs.get("headers", {})
        headers.update(request_headers)
        headers["referer"] = referer
        headers["content-type"] = content_type
        kwargs["headers"] = headers

        resp = await self._sess.request(method, AQUAREA_SERVICE_BASE + url, **kwargs)

        # Aquarea returns a 200 even if the request failed, we need to check the message property to see if it's an error
        # Some errors just require to login again, so we raise a AuthenticationError in those known cases
        errors = [FaultError]
        if throw_on_error:
            errors = await self.look_for_errors(resp)
            # If we have errors, let's look for authentication errors
            for error in errors:
                if error.error_code in list(AuthenticationErrorCodes):
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
                cool_mode = zone_record["coolMode"] == "enable"
                zone = DeviceZoneInfo(
                    zone_record["zoneId"],
                    zone_record["zoneName"],
                    zone_record["zoneType"],
                    cool_mode,
                    ZoneSensor(zone_record["zoneSensor"]),
                    SensorMode(zone_record["heatSensor"]),
                    SensorMode(zone_record["coolSensor"]) if cool_mode else None,
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
        operation_mode_value = device.get("operationMode")

        device_status = DeviceStatus(
            long_id,
            OperationStatus(device.get("operationStatus")),
            OperationStatus(device.get("deiceStatus")),
            device.get("outdoorNow"),
            ExtendedOperationMode.OFF
            if operation_mode_value == 99
            else ExtendedOperationMode(operation_mode_value),
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
                    zone_status["heatMax"],
                    zone_status["heatMin"],
                    zone_status["heatSet"],
                    zone_status["coolMax"],
                    zone_status["coolMin"],
                    zone_status["coolSet"],
                )
                for zone_status in device.get("zoneStatus", [])
            ],
            QuietMode(device.get("quietMode", 0))
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

    @auth_required
    async def post_device_operation_status(
        self, long_device_id: str, new_operation_status: OperationStatus
    ) -> None:
        """Post device operation status"""
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
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
            content_type="application/json",
            json=data,
        )

        return None

    @auth_required
    async def post_device_tank_temperature(
        self, long_device_id: str, new_temperature: int
    ) -> None:
        """Post device tank temperature"""
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
            f"{AQUAREA_SERVICE_DEVICES}/{long_device_id}",
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
            content_type="application/json",
            json=data,
        )

    @auth_required
    async def post_device_tank_operation_status(
        self,
        long_device_id: str,
        new_operation_status: OperationStatus,
        new_device_operation_status: OperationStatus = OperationStatus.ON,
    ) -> None:
        """Post device tank operation status"""
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
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
            content_type="application/json",
            json=data,
        )

    @auth_required
    async def post_device_operation_update(
        self,
        long_id: str,
        mode: UpdateOperationMode,
        zones: dict[int, OperationStatus],
        operation_status: OperationStatus.ON,
    ) -> None:
        """Post device operation update"""
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
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
            content_type="application/json",
            json=data,
        )

    async def post_device_zone_heat_temperature(
        self, long_id: str, zone_id: int, temperature: int
    ) -> None:
        """Post device zone heat temperature"""
        return await self._post_device_zone_temperature(
            long_id, zone_id, temperature, "heatSet"
        )

    async def post_device_zone_cool_temperature(
        self, long_id: str, zone_id: int, temperature: int
    ) -> None:
        """Post device zone cool temperature"""
        return await self._post_device_zone_temperature(
            long_id, zone_id, temperature, "coolSet"
        )

    @auth_required
    async def _post_device_zone_temperature(
        self, long_id: str, zone_id: int, temperature: int, key: str
    ) -> None:
        """Post device zone temperature"""
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
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
            content_type="application/json",
            json=data,
        )

    @auth_required
    async def post_set_quiet_mode(
        self, long_id: str, mode: QuietMode
    ) -> None:
        """Post quiet mode"""
        data = {
            "status": [
                {
                    "deviceGuid": long_id,
                    "quietMode": mode.value
                }
            ]
        }

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
            content_type="application/json",
            json=data,
        )

    async def get_device_consumption(
        self, long_id: str, aggregation: DateType, date_input: str
    ) -> Consumption:
        """Get device consumption"""
        response = await self.request(
            "GET",
            f"{AQUAREA_SERVICE_CONSUMPTION}/{long_id}?{aggregation}={date_input}",
            referer=AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
        )

        date_data = await response.json()
        return Consumption(date_data.get("dateData")[0])


class TankImpl(Tank):
    """Tank implementation"""

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
    """Device implementation able to auto-refresh using the Aquarea Client"""

    def __init__(self, info: DeviceInfo, status: DeviceStatus, client: Client) -> None:
        super().__init__(info, status)
        self._client = client

        if self.has_tank:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

    async def refresh_data(self) -> None:
        self._status = await self._client.get_device_status(self._info.long_id)

        if self.has_tank:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

        self.__build_zones__()

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
                    if UpdateOperationMode.OFF == mode
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

    async def set_quiet_mode(
        self, mode: QuietMode
    ) -> None:
        await self._client.post_set_quiet_mode(self.long_id, mode)
