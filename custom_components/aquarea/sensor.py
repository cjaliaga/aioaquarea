"""Adds Aquarea sensors."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, Self
from .aioaquarea import ConsumptionType, DataNotAvailableError, DeviceDirection
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from . import AquareaBaseEntity
from .const import DEVICES, DOMAIN
from .coordinator import AquareaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(kw_only=True)
class AquareaEnergyConsumptionSensorDescription(SensorEntityDescription):
    """Entity Description for Aquarea Energy Consumption Sensors."""

    consumption_type: ConsumptionType
    exists_fn: Callable[[AquareaDataUpdateCoordinator],bool] = lambda _: True


ACCUMULATED_ENERGY_SENSORS: list[AquareaEnergyConsumptionSensorDescription] = [
    AquareaEnergyConsumptionSensorDescription(
        key="heating_accumulated_energy_consumption",
        name="Heating Monthly Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.HEAT,
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="cooling_accumulated_energy_consumption",
        name= "Cooling Monthly Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.COOL,
        exists_fn=lambda coordinator: any(zone.cool_mode for zone in coordinator.device.zones.values())
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="tank_accumulated_energy_consumption",
        name= "Tank Monthly Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.WATER_TANK,
        exists_fn=lambda coordinator: coordinator.device.has_tank
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="accumulated_energy_consumption",
        name= "Monthly Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.TOTAL
    ),
]
ENERGY_SENSORS: list[AquareaEnergyConsumptionSensorDescription] = [
    AquareaEnergyConsumptionSensorDescription(
        key="heating_energy_consumption",
        name="Heating Today's Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.HEAT,
        entity_registry_enabled_default=False
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="tank_energy_consumption",
        name= "Tank Today's Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.WATER_TANK,
        exists_fn=lambda coordinator: coordinator.device.has_tank,
        entity_registry_enabled_default=False
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="cooling_energy_consumption",
        name= "Cooling Today's Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.COOL,
        exists_fn=lambda coordinator: any(zone.cool_mode for zone in coordinator.device.zones.values()),
        entity_registry_enabled_default=True
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="energy_consumption",
        name= "Today's Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=5, # Increased precision
        consumption_type=ConsumptionType.TOTAL,
        entity_registry_enabled_default=False
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aquarea sensors from config entry."""
    data: dict[str, AquareaDataUpdateCoordinator] = hass.data[DOMAIN][
        config_entry.entry_id
    ][DEVICES]
    entities: list[SensorEntity] = []
    for coordinator in data.values():
        entities.append(OutdoorTemperatureSensor(coordinator))
        entities.extend(
            [
                EnergyAccumulatedConsumptionSensor(description,coordinator)
                for description in ACCUMULATED_ENERGY_SENSORS
                if description.exists_fn(coordinator)
            ]
        )
        entities.extend(
            [
                EnergyConsumptionSensor(description,coordinator)
                for description in ENERGY_SENSORS
                if description.exists_fn(coordinator)
            ]
        )
        entities.append(AquareaDirectionSensor(coordinator))
        entities.append(AquareaPumpDutySensor(coordinator))
    async_add_entities(entities)


@dataclass
class AquareaSensorExtraStoredData(SensorExtraStoredData):
    """Class to hold Aquarea sensor specific state data."""

    period_being_processed: datetime | None = None

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self:
        """Return AquareaSensorExtraStoredData from dict."""
        sensor_data = super().from_dict(restored)
        return cls(
            native_value=sensor_data.native_value,
            native_unit_of_measurement=sensor_data.native_unit_of_measurement,
            period_being_processed=dt_util.parse_datetime(
                restored.get("period_being_processed","")
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return AquareaSensorExtraStoredData as dict."""
        data = super().as_dict()
        if self.period_being_processed is not None:
            data["period_being_processed"] = dt_util.as_local(
                self.period_being_processed
            ).isoformat()
        return data


@dataclass
class AquareaAccumulatedSensorExtraStoredData(AquareaSensorExtraStoredData):
    """Class to hold Aquarea sensor specific state data."""

    accumulated_period_being_processed: float | None = None

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self:
        """Return AquareaSensorExtraStoredData from dict."""
        sensor_data = super().from_dict(restored)
        return cls(
            native_value=sensor_data.native_value,
            native_unit_of_measurement=sensor_data.native_unit_of_measurement,
            period_being_processed=sensor_data.period_being_processed,
            accumulated_period_being_processed=restored[
                "accumulated_period_being_processed"
            ],
        )

    def as_dict(self) -> dict[str, Any]:
        """Return AquareaAccumulatedSensorExtraStoredData as dict."""
        data = super().as_dict()
        data[
            "accumulated_period_being_processed"
        ] = self.accumulated_period_being_processed
        return data


class OutdoorTemperatureSensor(AquareaBaseEntity, SensorEntity):
    """Representation of a Aquarea sensor."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize outdoor temperature sensor."""
        super().__init__(coordinator)
        self._attr_name = "Outdoor Temperature"
        self._attr_unique_id = f"{super().unique_id}_outdoor_temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Updating sensor '%s' of %s",
            "outdoor_temperature",
            self.coordinator.device.device_name,
        )
        self._attr_native_value = self.coordinator.device.temperature_outdoor
        super()._handle_coordinator_update()


class EnergyAccumulatedConsumptionSensor(
    AquareaBaseEntity, SensorEntity, RestoreEntity
):
    """Representation of a Aquarea sensor."""

    entity_description: AquareaEnergyConsumptionSensorDescription

    def __init__(
        self,
        description: AquareaEnergyConsumptionSensorDescription,
        coordinator: AquareaDataUpdateCoordinator
    ) -> None:
        """Initialize an accumulated energy consumption sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{super().unique_id}_{description.key}"
        )
        self._period_being_processed: datetime | None = None
        self._accumulated_period_being_processed: float | None = None
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        if (sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = sensor_data.native_value
            self._period_being_processed = sensor_data.period_being_processed
            self._accumulated_period_being_processed = (
                sensor_data.accumulated_period_being_processed
            )
        if self._attr_native_value is None:
            self._attr_native_value = 0
        if self._accumulated_period_being_processed is None:
            self._accumulated_period_being_processed = 0
        await super().async_added_to_hass()

    @property
    def extra_restore_state_data(self) -> AquareaAccumulatedSensorExtraStoredData:
        """Return sensor specific state data to be restored."""
        return AquareaAccumulatedSensorExtraStoredData(
            self.native_value, self.native_unit_of_measurement, self.period_being_processed,
        )

    async def async_get_last_sensor_data(
        self,
    ) -> AquareaAccumulatedSensorExtraStoredData | None:
        """Restore native_value and native_unit_of_measurement."""
        if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
            return None
        return AquareaAccumulatedSensorExtraStoredData.from_dict(
            restored_last_extra_data.as_dict()
        )

    @property
    def period_being_processed(self) -> datetime | None:
        """Return the period being processed."""
        return self._period_being_processed

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Updating sensor '%s' of %s",
            self.unique_id,
            self.coordinator.device.device_name,
        )
        device = self.coordinator.device
        current_month_data = device._consumption # Access the internal dictionary directly

        total_consumption_for_month = 0.0
        for date, consumption_obj in current_month_data.items():
            # Only sum up data for the current month and up to the current day
            if date.month == dt_util.now().month and date.year == dt_util.now().year and date.day <= dt_util.now().day:
                value = None
                if self.entity_description.consumption_type == ConsumptionType.HEAT:
                    value = consumption_obj.heat_consumption
                elif self.entity_description.consumption_type == ConsumptionType.COOL:
                    value = consumption_obj.cool_consumption
                elif self.entity_description.consumption_type == ConsumptionType.WATER_TANK:
                    value = consumption_obj.tank_consumption
                elif self.entity_description.consumption_type == ConsumptionType.TOTAL:
                    value = consumption_obj.total_consumption
                
                if value is not None:
                    total_consumption_for_month += value
        
        _LOGGER.debug("Calculated accumulated consumption for %s: %s", self.unique_id, total_consumption_for_month)
        self._attr_native_value = total_consumption_for_month
        super()._handle_coordinator_update()


class EnergyConsumptionSensor(AquareaBaseEntity, SensorEntity, RestoreEntity):
    """Representation of a Aquarea sensor."""

    entity_description: AquareaEnergyConsumptionSensorDescription

    def __init__(
        self,
        description: AquareaEnergyConsumptionSensorDescription,
        coordinator: AquareaDataUpdateCoordinator
    ) -> None:
        """Initialize an accumulated energy consumption sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{super().unique_id}_{description.key}"
        )
        self._period_being_processed: datetime | None = None
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        if (sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = sensor_data.native_value
            self._period_being_processed = sensor_data.period_being_processed
        if self._attr_native_value is None:
            self._attr_native_value = 0
        await super().async_added_to_hass()

    @property
    def extra_restore_state_data(self) -> AquareaSensorExtraStoredData:
        """Return sensor specific state data to be restored."""
        return AquareaSensorExtraStoredData(
            self.native_value, self.native_unit_of_measurement, self.period_being_processed,
        )

    async def async_get_last_sensor_data(self) -> AquareaSensorExtraStoredData | None:
        """Restore native_value and native_unit_of_measurement."""
        if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
            return None
        return AquareaSensorExtraStoredData.from_dict(
            restored_last_extra_data.as_dict()
        )

    @property
    def period_being_processed(self) -> datetime | None:
        """Return the period being processed."""
        return self._period_being_processed

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Updating sensor '%s' of %s",
            self.unique_id,
            self.coordinator.device.device_name,
        )
        device = self.coordinator.device
        today = dt_util.now().date()

        try:
            # Get the daily consumption for today
            daily_consumption = device.get_or_schedule_consumption(
                dt_util.now(), self.entity_description.consumption_type
            )
            _LOGGER.debug("Daily consumption for %s (%s): %s", today, self.entity_description.consumption_type, daily_consumption)
            self._attr_native_value = daily_consumption if daily_consumption is not None else 0.0
        except DataNotAvailableError:
            _LOGGER.debug("Consumption data for %s is not yet available for sensor %s", today, self.unique_id)
            self._attr_native_value = 0.0 # Set to 0 if data is not available
        except Exception as ex:
            _LOGGER.error("Error updating sensor %s: %s", self.unique_id, ex)
            self._attr_native_value = 0.0 # Set to 0 on error

        super()._handle_coordinator_update()


class AquareaDirectionSensor(AquareaBaseEntity, SensorEntity):
    """Representation of a Aquarea sensor for device direction."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize the direction sensor."""
        super().__init__(coordinator)
        self._attr_name = "Direction"
        self._attr_unique_id = f"{super().unique_id}_direction"
        self._attr_icon = "mdi:compass"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Updating sensor '%s' of %s",
            "direction",
            self.coordinator.device.device_name,
        )
        self._attr_native_value = self.coordinator.device.current_direction.name
        super()._handle_coordinator_update()


class AquareaPumpDutySensor(AquareaBaseEntity, SensorEntity):
    """Representation of a Aquarea sensor for pump duty."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize the pump duty sensor."""
        super().__init__(coordinator)
        self._attr_name = "Pump Status"
        self._attr_unique_id = f"{super().unique_id}_pump_status"
        self._attr_state_class = SensorStateClass.MEASUREMENT # Keep as measurement for 0/1
        # No native_unit_of_measurement as it's a binary state (0 or 1)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:pump-off" if self.coordinator.device.pump_duty == 0 else "mdi:pump"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Updating sensor '%s' of %s",
            "pump_status",
            self.coordinator.device.device_name,
        )
        self._attr_native_value = self.coordinator.device.pump_duty
        super()._handle_coordinator_update()
