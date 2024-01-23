"""Aquarea Client foy asyncio."""
from __future__ import annotations

import asyncio
import datetime as dt
import functools
import logging
from typing import Optional
import urllib.parse

import aiohttp

from .const import (
    AQUAREA_SERVICE_A2W_STATUS_DISPLAY,
    AQUAREA_SERVICE_BASE,
    AQUAREA_SERVICE_CONSUMPTION,
    AQUAREA_SERVICE_CONTRACT,
    AQUAREA_SERVICE_DEMO_BASE,
    AQUAREA_SERVICE_DEVICES,
    AQUAREA_SERVICE_LOGIN,
    AquareaEnvironment,
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
)
from .errors import (
    ApiError,
    AuthenticationError,
    AuthenticationErrorCodes,
    DataNotAvailableError,
    InvalidData,
)
from .statistics import Consumption, ConsumptionType, DateType


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
        if not self._token_expiration:
            return False

        now = dt.datetime.astimezone(dt.datetime.utcnow(), tz=dt.timezone.utc)
        return now < self._token_expiration

    @property
    def logger(self) -> logging.Logger:
        """Return the logger."""
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
        """Make a request to Aquarea and return the response."""

        headers = self._HEADERS.copy()
        request_headers = kwargs.get("headers", {})
        headers.update(request_headers)
        headers["referer"] = referer
        headers["content-type"] = content_type
        kwargs["headers"] = headers

        resp = await self._sess.request(method, self._base_url + url, **kwargs)

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
        """Look for errors in the response and return them as a list of FaultError objects."""
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
        """Login to Aquarea and stores a token in the session."""
        intent = dt.datetime.now()
        await self._login_lock.acquire()
        try:
            if self._last_login > intent:
                return

            if self._environment is AquareaEnvironment.DEMO:
                await self._login_demo()
            else:
                await self._login_production()

            self._last_login = dt.datetime.now()

        finally:
            self._login_lock.release()

    async def _login_demo(self) -> None:
        _ = await self.request("GET", "", referer=self._base_url)
        self._token_expiration = dt.datetime.astimezone(
            dt.datetime.utcnow(), tz=dt.timezone.utc
        ) + dt.timedelta(days=1)

    async def _login_production(self) -> None:
        params = {
            "var.inputOmit": "false",
            "var.loginId": self.username,
            "var.password": self.password,
        }

        response: aiohttp.ClientResponse = await self.request(
            "POST",
            AQUAREA_SERVICE_LOGIN,
            referer=self._base_url,
            data=urllib.parse.urlencode(params),
        )

        data = await response.json()

        if not isinstance(data, dict):
            raise InvalidData(data)

        self._token_expiration = dt.datetime.strptime(
            data["accessToken"]["expires"], "%Y-%m-%dT%H:%M:%S%z"
        )

        self._logger.info(
            f"Login successful for {self.username}. Access Token Expiration: {self._token_expiration}"
        )

    @auth_required
    async def get_devices(self, include_long_id=False) -> list[DeviceInfo]:
        """Get list of devices and its configuration, without status."""
        response = await self.request("GET", AQUAREA_SERVICE_DEVICES)
        data = await response.json()

        if not isinstance(data, dict):
            raise InvalidData(data)

        devices: list[DeviceInfo] = []

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
        """Retrives device long id to be used to retrive device status."""
        cookies = dict(selectedGwid=device_id)

        if self._environment is AquareaEnvironment.DEMO:
            return (
                self._sess.cookie_jar.filter_cookies(self._base_url)
                .get("selectedDeviceId")
                .value
            )

        resp = await self.request(
            "POST",
            AQUAREA_SERVICE_CONTRACT,
            referer=self._base_url,
            cookies=cookies,
        )
        return resp.cookies.get("selectedDeviceId").value

    @auth_required
    async def get_device_status(self, long_id: str) -> DeviceStatus:
        """Retrives device status."""
        params = {"var.deviceDirect": "1"} if self._device_direct else {}
        response = await self.request(
            "GET",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            referer=self._base_url,
            params=params,
        )
        data = await response.json()

        device = data.get("status")[0]
        operation_mode_value = device.get("operationMode")

        enabled_special_modes = [
            mode["specialMode"]
            for mode in device.get("specialStatus", [])
            if mode.get("operationStatus") == 1
        ]

        device_status = DeviceStatus(
            long_id=long_id,
            operation_status=OperationStatus(device.get("operationStatus")),
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
            ],
            zones=[
                DeviceZoneStatus(
                    zone_id=zone_status["zoneId"],
                    temperature=zone_status["temparatureNow"],
                    operation_status=OperationStatus(zone_status["operationStatus"]),
                    heat_max=zone_status["heatMax"],
                    heat_min=zone_status["heatMin"],
                    heat_set=zone_status["heatSet"],
                    cool_max=zone_status["coolMax"],
                    cool_min=zone_status["coolMin"],
                    cool_set=zone_status["coolSet"],
                    comfort_cool=zone_status["comfortCool"],
                    comfort_heat=zone_status["comfortHeat"],
                    eco_cool=zone_status["ecoCool"],
                    eco_heat=zone_status["ecoHeat"],
                )
                for zone_status in device.get("zoneStatus", [])
            ],
            quiet_mode=QuietMode(device.get("quietMode", 0)),
            force_dhw=ForceDHW(device.get("forceDHW", 0)),
            force_heater=ForceHeater(device.get("forceHeater", 0)),
            holiday_timer=HolidayTimer(device.get("holidayTimer", 0)),
            powerful_time=PowerfulTime(device.get("powerful", 0)),
            special_status=SpecialStatus(enabled_special_modes[0])
            if enabled_special_modes
            else None,
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
            devices = await self.get_devices(include_long_id=True)
            device_info = next(
                filter(lambda d: d.device_id == device_id, devices), None
            )

        return DeviceImpl(
            device_info,
            await self.get_device_status(device_info.long_id),
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            f"{AQUAREA_SERVICE_DEVICES}/{long_device_id}",
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
            json=data,
        )

    @auth_required
    async def post_device_set_quiet_mode(self, long_id: str, mode: QuietMode) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "quietMode": mode.value}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
            json=data,
        )

    @auth_required
    async def post_device_force_dhw(self, long_id: str, force_dhw: ForceDHW) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "forceDHW": force_dhw.value}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
            json=data,
        )

    @auth_required
    async def post_device_request_defrost(self, long_id: str) -> None:
        """Post quiet mode."""
        data = {"status": [{"deviceGuid": long_id, "forcedefrost": 1}]}

        response = await self.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
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
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            content_type="application/json",
            json=data,
        )

    async def get_device_consumption(
        self, long_id: str, aggregation: DateType, date_input: str
    ) -> Consumption:
        """Get device consumption."""
        response = await self.request(
            "GET",
            f"{AQUAREA_SERVICE_CONSUMPTION}/{long_id}?{aggregation}={date_input}",
            referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
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

        if self.has_tank:
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
            self.long_id, DateType.DAY, day.strftime("%Y-%m-%d")
        )

        return self._consumption[day].energy.get(consumption_type)[date.hour]

    def get_or_schedule_consumption(
        self, date: dt.datetime, consumption_type: ConsumptionType
    ) -> float | None:
        """Get available consumption data or schedules retrieval for the next refresh cycle.

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
