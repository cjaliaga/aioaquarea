from __future__ import annotations

from typing import TYPE_CHECKING

from .auth import PanasonicRequestHeader
from .const import AQUAREA_SERVICE_A2W_STATUS_DISPLAY, AQUAREA_SERVICE_DEVICES
from .data import (
    DeviceZoneStatus,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    OperationStatus,
    PendingDeviceUpdates,
    PowerfulTime,
    QuietMode,
    SpecialStatus,
    UpdateOperationMode,
    ZoneTemperatureSetUpdate,
)

if TYPE_CHECKING:
    from .api_client import AquareaAPIClient


class AquareaDeviceControl:
    """Handles device control operations."""

    def __init__(self, api_client: AquareaAPIClient, base_url: str):
        self._api_client = api_client
        self._base_url = base_url

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

        await self._api_client.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_device_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
            ),
            json=data,
        )

    async def post_device_tank_temperature(
        self, long_device_id: str, new_temperature: int
    ) -> None:
        """Post device tank temperature."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {
                "gwid": long_device_id,
                "tankStatus": {
                    "heatSet": new_temperature,
                },
            },
        }

        await self._api_client.request(
            "POST",
            url="remote/v1/app/common/transfer",  # Specific URL for transfer API
            json=data,
            throw_on_error=True,
        )

    async def post_device_tank_operation_status(
        self,
        long_device_id: str,
        new_operation_status: OperationStatus,
        zones: list[DeviceZoneStatus],
    ) -> None:
        """Post device tank operation status."""
        zone_status_list = []
        for zone in zones:
            zone_status_list.append(
                {
                    "zoneId": zone.zone_id,
                    "operationStatus": zone.operation_status.value,
                }
            )

        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {
                "gwid": long_device_id,
                "zoneStatus": zone_status_list,
                "tankStatus": {"operationStatus": new_operation_status.value},
            },
        }

        await self._api_client.request(
            "POST",
            url="remote/v1/app/common/transfer",  # Specific URL for transfer API
            json=data,
            throw_on_error=True,
        )

    async def post_device_operation_update(
        self,
        long_id: str,
        mode: UpdateOperationMode,
        zones: dict[int, OperationStatus],
        operation_status: OperationStatus,
        tank_operation_status: OperationStatus,
        zone_temperature_updates: list[ZoneTemperatureSetUpdate]
        | None = None,  # New parameter
    ) -> None:
        """Post device operation update."""
        # Construct zoneStatus list based on provided zones and optional temperature updates
        zone_status_list = []
        for zone_id, op_status in zones.items():
            zone_data = {
                "zoneId": zone_id,
                "operationStatus": op_status.value,
            }
            if zone_temperature_updates:
                for temp_update in zone_temperature_updates:
                    if temp_update.zone_id == zone_id:
                        if temp_update.heat_set is not None:
                            zone_data["heatSet"] = temp_update.heat_set
                        if temp_update.cool_set is not None:
                            zone_data["coolSet"] = temp_update.cool_set
                        break
            zone_status_list.append(zone_data)

        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {
                "gwid": long_id,
                "operationMode": mode.value,
                "operationStatus": operation_status.value,
                "zoneStatus": zone_status_list,
                "tankStatus": {"operationStatus": tank_operation_status.value},
            },
        }

        await self._api_client.request(
            "POST",
            url="remote/v1/app/common/transfer",  # Specific URL for transfer API
            json=data,
            throw_on_error=True,
        )

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

        await self._api_client.request(
            "POST",
            f"{AQUAREA_SERVICE_DEVICES}/{long_id}",
            headers=PanasonicRequestHeader.get_aqua_headers(
                content_type="application/json",
                referer=f"{self._base_url}{AQUAREA_SERVICE_A2W_STATUS_DISPLAY}",
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

    async def _post_device_zone_temperature(
        self, long_id: str, zone_id: int, temperature: int, key: str
    ) -> None:
        """Post device zone temperature."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {
                "gwid": long_id,
                "zoneStatus": [
                    {
                        "zoneId": zone_id,
                        key: temperature,
                    }
                ],
            },
        }

        response = await self._api_client.request(
            "POST",
            "/remote/v1/app/common/transfer",
            headers={},
            json=data,
        )

    async def post_device_set_quiet_mode(self, long_id: str, mode: QuietMode) -> None:
        """Post quiet mode."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {"gwid": long_id, "quietMode": mode.value},
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )

    async def post_device_force_dhw(self, long_id: str, force_dhw: ForceDHW) -> None:
        """Post force DHW command."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {"gwid": long_id, "forceDHW": force_dhw.value},
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )

    async def post_device_force_heater(
        self, long_id: str, force_heater: ForceHeater
    ) -> None:
        """Post force heater command."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {"gwid": long_id, "forceHeater": force_heater.value},
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )

    async def post_device_holiday_timer(
        self, long_id: str, holiday_timer: HolidayTimer
    ) -> None:
        """Post holidayTimer command."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {"gwid": long_id, "holidayTimer": holiday_timer.value},
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )

    async def post_device_request_defrost(self, long_id: str) -> None:
        """Post forcedefrost command."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {"gwid": long_id, "forcedefrost": 1},
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )

    async def post_device_set_powerful_time(
        self, long_id: str, powerful_time: PowerfulTime
    ) -> None:
        """Post powerful time."""
        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": {"gwid": long_id, "powerfulRequest": powerful_time.value},
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )

    async def post_device_batch_update(
        self, long_id: str, updates: PendingDeviceUpdates
    ) -> None:
        """Post a batch of device updates in a single API call.

        Merges all pending changes into one transfer API request.
        :param long_id: The device GUID
        :param updates: The pending updates to apply
        """
        body_param: dict = {"gwid": long_id}

        if updates.operation_mode is not None:
            body_param["operationMode"] = updates.operation_mode.value

        if updates.operation_status is not None:
            body_param["operationStatus"] = updates.operation_status.value

        if updates.zone_updates is not None:
            body_param["zoneStatus"] = [
                {"zoneId": zid, "operationStatus": op.value}
                for zid, op in updates.zone_updates.items()
            ]

        if updates.zone_temperature_updates is not None:
            zone_status = body_param.get("zoneStatus", [])
            existing_zones = {z["zoneId"]: z for z in zone_status}
            for temp_update in updates.zone_temperature_updates:
                if temp_update.zone_id in existing_zones:
                    if temp_update.heat_set is not None:
                        existing_zones[temp_update.zone_id]["heatSet"] = temp_update.heat_set
                    if temp_update.cool_set is not None:
                        existing_zones[temp_update.zone_id]["coolSet"] = temp_update.cool_set
                else:
                    entry = {"zoneId": temp_update.zone_id}
                    if temp_update.heat_set is not None:
                        entry["heatSet"] = temp_update.heat_set
                    if temp_update.cool_set is not None:
                        entry["coolSet"] = temp_update.cool_set
                    zone_status.append(entry)
            if not body_param.get("zoneStatus"):
                body_param["zoneStatus"] = zone_status

        tank_status: dict = {}
        if updates.tank_operation_status is not None:
            tank_status["operationStatus"] = updates.tank_operation_status.value
        if updates.tank_temperature is not None:
            tank_status["heatSet"] = updates.tank_temperature
        if tank_status:
            body_param["tankStatus"] = tank_status

        if updates.quiet_mode is not None:
            body_param["quietMode"] = updates.quiet_mode.value
        if updates.force_dhw is not None:
            body_param["forceDHW"] = updates.force_dhw.value
        if updates.force_heater is not None:
            body_param["forceHeater"] = updates.force_heater.value
        if updates.holiday_timer is not None:
            body_param["holidayTimer"] = updates.holiday_timer.value
        if updates.powerful_time is not None:
            body_param["powerfulRequest"] = updates.powerful_time.value
        if updates.request_defrost:
            body_param["forcedefrost"] = 1

        data = {
            "apiName": "/remote/v1/api/devices",
            "requestMethod": "POST",
            "bodyParam": body_param,
        }

        await self._api_client.request(
            "POST",
            "remote/v1/app/common/transfer",
            json=data,
            throw_on_error=True,
        )
