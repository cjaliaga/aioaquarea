"""Aquarea Client foy asyncio."""
from __future__ import annotations

import functools
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from .errors import InvalidData, RequestFailedError
from .const import AQUAREA_SERVICE_BASE, AQUAREA_SERVICE_CONTRACT, AQUAREA_SERVICE_DEVICES, AQUAREA_SERVICE_LOGIN
from .data import Device, DeviceInfo, DeviceStatus, DeviceZone, DeviceZoneStatus, ExtendedOperationMode, FaultError, OperationMode, OperationStatus, SensorMode, Tank


def auth_required(fn):
    @functools.wraps(fn)
    async def _wrap(client, *args, **kwargs):
        if client.is_logged is False:
            client._logger.warning(
                f"{client}: User is not logged or session is too old"
            )
            await client.login()

        return await fn(client, *args, **kwargs)

    return _wrap

class Client:
    _HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "max-age=0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/74.0"
    }

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        logger: Optional[logging.Logger] = None,
    ):

        self._sess = session
        self._username = username
        self._password = password
        self._logger = logger or logging.getLogger("aioaquarea")
        self._token_expiration: Optional[datetime] = None

    @property
    def username(self) -> str:
        return self._username

    @property
    def password(self) -> str:
        return self._password
    
    @property
    def token_expiration(self) -> Optional[datetime]:
        return self._token_expiration

    @property
    def is_logged(self) -> bool:
        if not self._token_expiration:
            return False

        now = datetime.astimezone(datetime.utcnow(), tz=timezone.utc)
        return now < self._token_expiration

    async def raw_request(
        self, method: str, url: str, referer: str, **kwargs
    ) -> aiohttp.ClientResponse:
        headers = kwargs.get("headers", {})
        headers.update(self._HEADERS)
        headers["referer"] = referer
        kwargs["headers"] = headers

        resp = await self._sess.request(method, AQUAREA_SERVICE_BASE + url, **kwargs)
        if resp.status != 200:
            raise RequestFailedError(resp)

        return resp

    async def request(self, method: str, url: str, referer: str=AQUAREA_SERVICE_BASE, **kwargs) -> Dict[str, Any]:
        resp = await self.raw_request(method, url, referer, **kwargs)

        if resp.status != 200:
            raise RequestFailedError(resp)

        return await resp.json()

    async def login(self) -> None:
        params = {
            "var.inputOmit": "false",
            "var.loginId": self.username,
            "var.password": self.password
        }

        data = await self.request("POST", AQUAREA_SERVICE_LOGIN, referer=AQUAREA_SERVICE_BASE, data=urllib.parse.urlencode(params))

        if not isinstance(data, dict):
            raise InvalidData(data)

        self._token_expiration = datetime.strptime(data['accessToken']['expires'], "%Y-%m-%dT%H:%M:%S%z")

        self._logger.info(
            f"Login successful for {self.username}. Access Token Expiration: {self._token_expiration}"
        )
    
    @auth_required
    async def get_devices(self, include_long_id=False) -> List[DeviceInfo]:
        """Get list of devices and its configuration, without status."""
        data = await self.request("GET", AQUAREA_SERVICE_DEVICES)

        if not isinstance(data, dict):
            raise InvalidData(data)

        devices: List[DeviceInfo] = []

        for record in data["device"]:
            zones = [DeviceZone]
       
            for zone_record in record["configration"][0]["zoneInfo"]:
                zone = DeviceZone(zone_record["zoneId"],
                                zone_record["zoneName"],
                                zone_record["zoneType"],
                                zone_record["coolMode"] == "enable",
                                SensorMode(zone_record["zoneSensor"]),
                                SensorMode(zone_record["heatSensor"]),
                                SensorMode(zone_record["coolSensor"])
                        )
                zones.append(zone)

            device_id = record["deviceGuid"]
            long_id = await self.get_device_long_id(device_id) if include_long_id else ""

            device = DeviceInfo(device_id,
                                record["configration"][0]["a2wName"],
                                long_id,
                                OperationMode(record["configration"][0]["operationMode"]),
                                record["configration"][0]["tankInfo"][0]["tank"] == "Yes",
                                record["configration"][0]["firmVersion"],
                                zones
                    )

            devices.append(device)

        return devices

    @auth_required
    async def get_device_long_id(self, device_id: str) -> str:
        """Retrives device long id to be used to retrive device status"""
        cookies = dict(selectedGwid=device_id)
        resp = await self.raw_request("POST", AQUAREA_SERVICE_CONTRACT, referer=AQUAREA_SERVICE_BASE, cookies=cookies)
        return resp.cookies.get("selectedDeviceId").value
    
    @auth_required
    async def get_device_status(self, long_id: str) -> DeviceStatus:
        """Retrives device status"""
        data = await self.request("GET", f"{AQUAREA_SERVICE_DEVICES}/{long_id}?var.deviceDirect=1")
        device = data.get("status")[0]

        device_status = DeviceStatus(long_id,
            OperationStatus(device.get("operationStatus")),
            OperationStatus(device.get("deiceStatus")),
            device.get("outdoorNow"),
            ExtendedOperationMode(device.get("operationMode")),
            [
                FaultError(fault_status["errorMessage"], fault_status["errorCode"]) 
                for fault_status
                in device.get("faultStatus", [])
            ],
            device.get("direction"),
            device.get("pumpDuty"),
            [
                Tank(
                    OperationStatus(tank_status["operationStatus"]),
                    tank_status["temparatureNow"],
                    tank_status["heatMax"],
                    tank_status["heatMin"],
                    tank_status["heatSet"]
                )
                for tank_status
                in device.get("tankStatus", [])
                ],
            [
                DeviceZoneStatus(zone_status["zoneId"], zone_status["temparatureNow"], OperationStatus(zone_status["operationStatus"]))
                for zone_status
                in device.get("zoneStatus", [])
            ]
        )

        return device_status
   
    @auth_required
    async def get_device(self, device_info: DeviceInfo | None = None, device_id: str | None = None) -> Device:
        """Retrieves device"""
        if not device_info and not device_id:
            raise ValueError("Either device_info or device_id must be provided")
       
        if not device_info:
            devices = await self.get_devices(include_long_id=True)
            device_info = next(filter(lambda d: d.device_id == device_id, devices), None)

        return DeviceImpl(device_info, await self.get_device_status(device_info.long_id), self)

class DeviceImpl(Device):
    """Device implementation able to auto-refresh using the Aquarea Client"""
    _long_id: str
    _name: str
    _operation_mode: ExtendedOperationMode
    _direction: int
    _status: int
    _temperature_outdoor: int
    _tank: Tank
    _firmware_version: str
    _zones: list[DeviceZoneStatus] = []

    def __init__(self, info: DeviceInfo, status: DeviceStatus, client: Client) -> None:
        super().__init__(info, status)
        self._client = client
   
    async def refresh_data(self) -> None:
        self._status = await self._client.get_device_status(self._info.long_id)
