import asyncio
import datetime as dt
import logging # Import logging
from typing import Optional, TYPE_CHECKING

from .data import (
    Device,
    DeviceInfo,
    DeviceModeStatus,
    DeviceStatus,
    OperationStatus,
    Tank,
    TankStatus,
    UpdateOperationMode,
    QuietMode,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    PowerfulTime,
    SpecialStatus,
    ZoneTemperatureSetUpdate,
    ExtendedOperationMode,
    StatusDataMode,
    DeviceZoneInfo,
    OperationMode,
)
from .errors import DataNotAvailableError
from .statistics import ConsumptionType, DateType

if TYPE_CHECKING:
    from .core import AquareaClient

_LOGGER = logging.getLogger(__name__) # Define logger

class TankImpl(Tank):
    """Tank implementation."""

    _client: "AquareaClient"

    def __init__(self, status: TankStatus, device: Device, client: "AquareaClient") -> None:
        super().__init__(status, device)
        self._client = client

    async def __set_target_temperature__(self, value: int) -> None:
        await self._client.post_device_tank_temperature(self._device.device_id, value)

    async def __set_operation_status__(
        self, status: OperationStatus, device_status: OperationStatus
    ) -> None:
        await self._client.post_device_tank_operation_status(
            self._device.device_id, status, device_status
        )


class DeviceImpl(Device):
    """Device implementation able to auto-refresh using the Aquarea Client."""

    def __init__(
        self,
        device_id: str,
        long_id: str,
        name: str,
        firmware_version: str,
        model: str,
        has_tank: bool,
        zones_info: list[DeviceZoneInfo],
        status: DeviceStatus,
        client: "AquareaClient",
        consumption_refresh_interval: Optional[dt.timedelta] = None,
        timezone: dt.timezone = dt.timezone.utc,
    ) -> None:
        # Create a DeviceInfo object from the individual arguments
        device_info = DeviceInfo(
            device_id=device_id,
            name=name,
            long_id=long_id,
            mode=OperationMode.Heat,
            has_tank=has_tank,
            firmware_version=firmware_version,
            model=model,
            zones=zones_info,
            status_data_mode=StatusDataMode.LIVE
        )
        super().__init__(device_info, status)
        self._client = client
        self._timezone = timezone
        self._last_consumption_refresh: dt.datetime | None = None
        self._consumption_refresh_lock = asyncio.Lock()
        self._consumption_refresh_interval = consumption_refresh_interval

        if self.has_tank and self._status.tank_status:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

    async def refresh_data(self, expected_temperature: int | None = None, zone_id: int | None = None) -> None:
        """Refreshes the device data, optionally waiting for a specific temperature."""
        max_retries = 5
        retry_delay = 1  # seconds
        
        _LOGGER.debug(f"Starting refresh_data for device {self.long_id}. Expected temp: {expected_temperature}, Zone ID: {zone_id}")

        for i in range(max_retries):
            _LOGGER.debug(f"Refresh attempt {i+1}/{max_retries} for device {self.long_id}.")
            self._status = await self._client.get_device_status(self._info)

            if expected_temperature is not None and zone_id is not None:
                zone_status_list = [z for z in self._status.zones if z.zone_id == zone_id]
                zone = zone_status_list[0] if zone_status_list else None

                if zone:
                    # Check if the current temperature matches the expected temperature
                    # Use the correct target temperature based on the current mode
                    if self.mode in (ExtendedOperationMode.COOL, ExtendedOperationMode.AUTO_COOL):
                        current_temp = zone.cool_target_temperature
                        _LOGGER.debug(f"Device mode is COOL/AUTO_COOL. Checking cool_target_temperature.")
                    else:
                        current_temp = zone.heat_target_temperature
                        _LOGGER.debug(f"Device mode is HEAT/AUTO_HEAT. Checking heat_target_temperature.")

                    if current_temp == expected_temperature:
                        _LOGGER.debug(f"Temperature for zone {zone_id} matched expected {expected_temperature} after {i+1} retries. Exiting polling loop.")
                        break # Temperature matched, exit loop
                else:
                    current_temp = None # Zone not found
                _LOGGER.debug(f"Temperature for zone {zone_id} is {current_temp}, expected {expected_temperature}. Retrying...")
            
            if i < max_retries - 1:
                await asyncio.sleep(retry_delay)
        else: # This block executes if the loop completes without a 'break'
            if expected_temperature is not None and zone_id is not None:
                _LOGGER.warning(f"Temperature for zone {zone_id} did not match expected {expected_temperature} after {max_retries} retries. Using last fetched value.")
            else:
                _LOGGER.debug(f"Refresh_data completed for device {self.long_id} without specific temperature expectation.")

        if self._consumption:
            await self.__refresh_consumption__()

        if self._consumption:
            await self.__refresh_consumption__()

    async def __refresh_consumption__(self) -> None:
        """Refreshes the consumption data."""
        # Temporarily disable consumption refresh as per user request for debugging
        _LOGGER.debug("Consumption refresh temporarily disabled.")
        return

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
            print("Zone does not support setting temperature.")
            return

        if self.mode in [ExtendedOperationMode.AUTO_COOL, ExtendedOperationMode.COOL]:
            print(f"Setting cool temperature for zone {zone_id} to {temperature}")
            await self._client.post_device_zone_cool_temperature(
                self.long_id, zone_id, temperature
            )
        elif self.mode in [ExtendedOperationMode.AUTO_HEAT, ExtendedOperationMode.HEAT]:
            print(f"Setting heat temperature for zone {zone_id} to {temperature}")
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
