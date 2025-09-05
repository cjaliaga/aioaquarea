import asyncio
import datetime as dt
import logging
from typing import TYPE_CHECKING, Optional

from .data import (
    Device,
    DeviceInfo,
    DeviceModeStatus,
    DeviceStatus,
    DeviceZoneInfo,
    ExtendedOperationMode,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    OperationMode,
    OperationStatus,
    PowerfulTime,
    QuietMode,
    SpecialStatus,
    StatusDataMode,
    Tank,
    TankStatus,
    UpdateOperationMode,
    ZoneTemperatureSetUpdate,
)
from .errors import DataNotAvailableError
from .statistics import Consumption, ConsumptionType, DateType

if TYPE_CHECKING:
    from .core import AquareaClient

_LOGGER = logging.getLogger(__name__)


class TankImpl(Tank):
    """Tank implementation."""

    _client: "AquareaClient"

    def __init__(
        self, status: TankStatus, device: Device, client: "AquareaClient"
    ) -> None:
        super().__init__(status, device)
        self._client = client

    async def __set_target_temperature__(self, value: int) -> None:
        await self._client.post_device_tank_temperature(self._device.device_id, value)

    async def __set_operation_status__(self, status: OperationStatus) -> None:
        # Get current zone statuses from the device
        zones_status = list(self._device.zones.values())
        await self._client.post_device_tank_operation_status(
            self._device.device_id, status, zones_status
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
            status_data_mode=StatusDataMode.LIVE,
        )
        super().__init__(device_info, status)
        self._client = client
        self._timezone = timezone
        self._last_consumption_refresh: dt.datetime | None = None
        self._consumption_refresh_lock = asyncio.Lock()
        self._consumption_refresh_interval = consumption_refresh_interval
        self._consumption: dict[
            dt.date, Consumption
        ] = {}  # Initialize _consumption with dt.date as key and single Consumption object for the day

        if self.has_tank and self._status.tank_status:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

        # The consumption data refresh is now triggered and awaited in AquareaClient.get_device
        # TODO
        # if self._consumption_refresh_interval:
        #     self.hass.async_create_task(self.__refresh_consumption__())

    @property
    def heat_max(self) -> int | None:
        """Gets the maximum allowed temperature for heat mode of the first zone"""
        zone = self.zones.get(1)
        return zone.heat_max if zone else None

    @property
    def cool_max(self) -> int | None:
        """Gets the maximum allowed temperature for cool mode of the first zone"""
        zone = self.zones.get(1)
        return zone.cool_max if zone else None

    async def refresh_data(self) -> None:
        self._status = await self._client.get_device_status(self._info)

        if self.has_tank and self._status.tank_status:
            self._tank = TankImpl(self._status.tank_status[0], self, self._client)

        if (
            self._consumption_refresh_interval
        ):  # Always attempt to refresh if interval is set
            await self.__refresh_consumption__()

    async def __refresh_consumption__(self) -> None:
        """Refreshes the consumption data."""
        if not self._consumption_refresh_interval:
            return

        if self._consumption_refresh_lock.locked():
            return

        await self._consumption_refresh_lock.acquire()

        try:
            now = dt.datetime.now(self._timezone)
            current_month = now.replace(
                day=1
            ).date()  # Get the first day of the current month

            # Check if we need to refresh for the current month
            if (
                self._last_consumption_refresh is None
                or (now - self._last_consumption_refresh)
                >= self._consumption_refresh_interval
                or not any(
                    d.month == current_month.month and d.year == current_month.year
                    for d in self._consumption.keys()
                )  # If it's a new month, refresh
            ):
                _LOGGER.debug(
                    "Refreshing consumption data for %s", current_month.strftime("%Y%m")
                )
                consumption_list = await self._client.get_device_consumption(
                    self.long_id,
                    DateType.MONTH,
                    now.strftime("%Y%m01"),  # Use YYYYMM01 for month mode
                )
                if consumption_list:
                    # Clear previous month's data if any
                    self._consumption.clear()
                    for item in consumption_list:
                        try:
                            # Parse dataTime to get the date for the key
                            item_date_str = item.data_time
                            if item_date_str:
                                # dataTime is YYYYMMDD for month mode
                                naive_dt = dt.datetime.strptime(item_date_str, "%Y%m%d")
                                utc_dt = naive_dt.replace(tzinfo=dt.timezone.utc)
                                item_date = utc_dt.date()
                                self._consumption[item_date] = item
                        except ValueError:
                            _LOGGER.warning(
                                "Could not parse date from consumption item: %s",
                                item.data_time,
                            )
                    self._last_consumption_refresh = now
                else:
                    _LOGGER.warning(
                        "Failed to retrieve consumption data for %s",
                        current_month.strftime("%Y%m"),
                    )
            else:
                _LOGGER.debug(
                    "Consumption data for %s is still fresh, skipping refresh",
                    current_month.strftime("%Y%m"),
                )

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

        tank_operation_status = (
            self.tank.operation_status
            if self.has_tank and self.tank
            else OperationStatus.OFF
        )

        # Prepare zone temperature updates to be sent along with operation mode
        zone_temperature_updates: list[ZoneTemperatureSetUpdate] = []
        for zone_id, zone_obj in self.zones.items():
            # Only include if the zone supports setting temperature
            if zone_obj.supports_set_temperature:
                zone_temperature_updates.append(
                    ZoneTemperatureSetUpdate(
                        zone_id=zone_id,
                        heat_set=zone_obj.heat_target_temperature,
                        cool_set=zone_obj.cool_target_temperature,
                    )
                )

        await self._client.post_device_operation_update(
            self.long_id,
            mode,
            zones,
            operation_status,
            tank_operation_status,
            zone_temperature_updates,
        )

    async def set_temperature(
        self, temperature: int, zone_id: int | None = None
    ) -> None:
        if not zone_id:
            _LOGGER.warning("No zone id provided to set_temperature")
            return

        zone = self.zones.get(zone_id)
        if not zone:
            _LOGGER.warning("Zone does not exist.")
            return

        if not zone.supports_set_temperature:
            _LOGGER.warning("Zone does not support setting temperature.")
            return

        if self.mode in [ExtendedOperationMode.AUTO_COOL, ExtendedOperationMode.COOL]:
            _LOGGER.info(
                f"Setting cool temperature for zone {zone_id} to {temperature}"
            )
            await self._client.post_device_zone_cool_temperature(
                self.long_id, zone_id, temperature
            )
        elif self.mode in [ExtendedOperationMode.AUTO_HEAT, ExtendedOperationMode.HEAT]:
            _LOGGER.info(
                f"Setting heat temperature for zone {zone_id} to {temperature}"
            )
            await self._client.post_device_zone_heat_temperature(
                self.long_id, zone_id, temperature
            )

    async def set_quiet_mode(self, mode: QuietMode) -> None:
        await self._client.post_device_set_quiet_mode(self.long_id, mode)

    async def get_and_refresh_consumption(
        self, date: dt.datetime, consumption_type: ConsumptionType
    ) -> float | None:
        """Retrieve consumption data and asynchronously refreshes if necessary for the specified date and type.

        :param date: The date to get the consumption for
        :param consumption_type: The consumption type to get.
        """
        day = date.date()
        await self.__refresh_consumption__()  # Ensure data is fresh

        consumption_obj = self._consumption.get(day)
        if not consumption_obj:
            raise DataNotAvailableError(f"Consumption for {day} is not yet available")

        if consumption_type == ConsumptionType.HEAT:
            return consumption_obj.heat_consumption
        elif consumption_type == ConsumptionType.COOL:
            return consumption_obj.cool_consumption
        elif consumption_type == ConsumptionType.WATER_TANK:
            return consumption_obj.tank_consumption
        elif consumption_type == ConsumptionType.TOTAL:
            return consumption_obj.total_consumption
        return None

    def get_or_schedule_consumption(
        self, date: dt.datetime, consumption_type: ConsumptionType
    ) -> float | None:
        """Gets available consumption data or schedules retrieval for the next refresh cycle.
        :param date: The date to get the consumption for
        :param consumption_type: The consumption type to get
        """
        day = date.date()
        consumption_obj = self._consumption.get(day)

        if not consumption_obj:
            # Schedule a refresh if data is not available
            # self.hass.async_create_task(self.__refresh_consumption__())
            raise DataNotAvailableError(
                f"Consumption for {day} is not yet available. Scheduling refresh."
            )

        if consumption_type == ConsumptionType.HEAT:
            return consumption_obj.heat_consumption
        elif consumption_type == ConsumptionType.COOL:
            return consumption_obj.cool_consumption
        elif consumption_type == ConsumptionType.WATER_TANK:
            return consumption_obj.tank_consumption
        elif consumption_type == ConsumptionType.TOTAL:
            return consumption_obj.total_consumption
        return None

    async def set_force_dhw(self, force_dhw: ForceDHW) -> None:
        """Set the force dhw.

        :param force_dhw: Set the Force DHW mode if the device has a tank.
        """
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
