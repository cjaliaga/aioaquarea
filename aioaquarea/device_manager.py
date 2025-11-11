import logging
from typing import TYPE_CHECKING

from .auth import CCAppVersion, PanasonicRequestHeader, PanasonicSettings
from .const import BASE_PATH_ACC
from .data import (
    DeviceDirection,
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
    PumpDuty,
    QuietMode,
    SensorMode,
    StatusDataMode,
    TankStatus,
)
from .errors import RequestFailedError  # Import RequestFailedError

if TYPE_CHECKING:
    from .core import AquareaClient

_LOGGER = logging.getLogger(__name__)


class DeviceManager:
    def __init__(
        self,
        client: "AquareaClient",
        settings: PanasonicSettings,
        app_version: CCAppVersion,
        logger: logging.Logger,
    ):
        self._client = client
        self._settings = settings
        self._app_version = app_version
        self._logger = logger
        self._groups = None
        self._devices: list[DeviceInfo] | None = None
        self._unknown_devices: list[DeviceInfo] = []
        self._device_indexer = {}

    async def get_devices(self) -> list[DeviceInfo]:
        """Get list of devices and its configuration, without status."""
        if self._devices is None:
            self._devices = []
            self._unknown_devices = []
            # Assuming self._client.request can be called directly or passed through
            # and BASE_PATH_ACC is accessible.
            # This part needs to be carefully integrated with the actual Client class.
            groups_response = await self._client._api_client.request(  # Changed to _api_client.request
                "GET",
                external_url=f"{BASE_PATH_ACC}/device/group",
                headers=await PanasonicRequestHeader.get(
                    self._settings, self._app_version
                ),
            )
            self._groups = await groups_response.json()

            if self._groups is not None and "groupList" in self._groups:
                for group in self._groups["groupList"]:
                    device_list = group.get("deviceList", [])
                    if not device_list:
                        device_list = group.get("deviceIdList", [])

                    for device_raw in device_list:
                        if device_raw and device_raw.get("deviceType") == "2":
                            _LOGGER.info(f"Raw device response: {device_raw}")
                            device_id = device_raw.get("deviceGuid")
                            device_name = device_raw.get("deviceName", "Unknown Device")
                            operation_mode = OperationMode(
                                device_raw.get("operationMode", 0)
                            )  # Default to 0 if not found
                            # Check if tankStatus exists, is not None, and is not an empty dict
                            tank_status = device_raw.get("tankStatus")
                            has_tank = bool(tank_status and tank_status != {})
                            firmware_version = (
                                "N/A"  # Mock data as it's not in the new structure
                            )
                            model = "N/A"  # Get model or use default

                            zones: list[DeviceZoneInfo] = []
                            device_operation_mode = device_raw.get("operationMode")
                            # Check if the device's overall operation mode indicates cooling support
                            device_supports_cooling = device_operation_mode in [
                                OperationMode.Cool.value,
                                ExtendedOperationMode.COOL.value,
                                ExtendedOperationMode.AUTO_COOL.value,
                            ]

                            for zone_record in device_raw.get("zoneStatus", []):
                                # Mock data for fields not present in the new zoneStatus structure
                                zone_id = zone_record.get("zoneId")
                                if zone_id is not None:
                                    # Prioritize coolMin/coolMax if present, otherwise infer from device's overall cooling support
                                    has_cool_mode = (
                                        "coolMin" in zone_record
                                        and "coolMax" in zone_record
                                    ) or device_supports_cooling
                                    zone = DeviceZoneInfo(
                                        zone_id,
                                        f"Zone {zone_id}",  # Mock zone name
                                        "Unknown",  # Mock zone type
                                        has_cool_mode,  # Determine cool_mode based on coolMin/coolMax presence
                                        SensorMode.DIRECT,  # Mock heat_sensor
                                        SensorMode.DIRECT,  # Mock cool_sensor
                                        SensorMode.DIRECT,  # Mock cool_sensor
                                    )
                                    zones.append(zone)

                            device_info = DeviceInfo(
                                device_id,
                                device_name,
                                device_id,  # long_id
                                operation_mode,
                                has_tank,
                                firmware_version,
                                model,  # Added model
                                zones,
                                StatusDataMode.LIVE,  # Added status_data_mode
                            )
                            _LOGGER.info(
                                f"get_devices: Device {device_id} has_tank: {has_tank}, raw device_raw: {device_raw}"
                            )
                            self._device_indexer[device_id] = device_id
                            self._devices.append(device_info)
        return self._devices + self._unknown_devices

    async def get_device_status(self, device_info: DeviceInfo) -> DeviceStatus:
        """Retrives device status."""
        json_response = None
        try:
            payload = {
                "apiName": f"/remote/v1/api/devices?gwid={device_info.device_id}&deviceDirect=1",
                "requestMethod": "GET",
            }
            response = await self._client._api_client.request(
                "POST",
                url="remote/v1/app/common/transfer",
                json=payload,
                throw_on_error=True,
            )
            json_response = await response.json()
            self._logger.info(
                f"get_device_status (live): Raw JSON response for device {device_info.device_id}: {json_response}"
            )
        except Exception as e:
            self._logger.warning(
                "Failed to get live status for device {}: {}".format(
                    device_info.device_id, e
                )
            )
            # If live data fails, try cached data as a fallback
            try:
                payload = {
                    "apiName": f"/remote/v1/api/devices?gwid={device_info.device_id}&deviceDirect=0",
                    "requestMethod": "GET",
                }
                response = await self._client._api_client.request(
                    "POST",
                    url="remote/v1/app/common/transfer",
                    json=payload,
                    throw_on_error=True,
                )
                json_response = await response.json()
                self._logger.info(
                    "Successfully retrieved cached status for device {} after live data failure. Raw JSON: {}".format(
                        device_info.device_id, json_response
                    )
                )
            except Exception as e_cached:
                self._logger.error(
                    "Failed to get cached status for device {}: {}".format(
                        device_info.device_id, e_cached
                    )
                )
                raise RequestFailedError(
                    "Failed to retrieve device status after multiple attempts."
                ) from e_cached

        if json_response is None:
            raise RequestFailedError(
                "Failed to retrieve device status after multiple attempts."
            )

        device = json_response.get("status")
        operation_mode_value = device.get("operationMode")

        device_status = DeviceStatus(
            long_id=device_info.device_id,  # Use device_info.long_id here
            operation_status=OperationStatus(device.get("specialStatus")),
            device_status=DeviceModeStatus(device.get("deiceStatus")),
            temperature_outdoor=device.get("outdoorNow"),
            operation_mode=(
                ExtendedOperationMode.OFF
                if operation_mode_value == 99
                else ExtendedOperationMode(operation_mode_value)
            ),
            fault_status=[
                FaultError(fault_status["errorMessage"], fault_status["errorCode"])
                for fault_status in device.get("faultStatus", [])
            ],
            direction=DeviceDirection(device.get("direction")),
            pump_duty=PumpDuty(device.get("pumpDuty")),
            tank_status=(
                [
                    TankStatus(
                        OperationStatus(
                            device.get("tankStatus", {}).get("operationStatus")
                        ),
                        device.get("tankStatus", {}).get("temperatureNow"),
                        device.get("tankStatus", {}).get("heatMax"),
                        device.get("tankStatus", {}).get("heatMin"),
                        device.get("tankStatus", {}).get("heatSet"),
                    )
                ]
                if device.get("tankStatus")
                else []
            ),
            zones=[
                DeviceZoneStatus(
                    zone_id=zone_status.get("zoneId"),
                    temperature=zone_status.get("temperatureNow"),
                    operation_status=OperationStatus(
                        zone_status.get("operationStatus")
                    ),
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
            special_status=None,  # Simplified to None
        )

        return device_status
