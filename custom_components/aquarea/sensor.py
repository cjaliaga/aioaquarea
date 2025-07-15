"""Support for Panasonic Aquarea sensors."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, AquareaDataUpdateCoordinator
from aioaquarea import Device, Consumption, ConsumptionType

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aquarea sensor platform."""
    coordinator: AquareaDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    entities = []
    for device_id, device in coordinator.data.items():
        # Current Temperature Sensor
        entities.append(
            AquareaSensor(
                coordinator,
                device_id,
                device,
                "current_temperature",
                "Current Temperature",
                UnitOfTemperature.CELSIUS,
                SensorDeviceClass.TEMPERATURE,
                SensorStateClass.MEASUREMENT,
            )
        )
        # Daily Consumption Sensor (example, assuming it's available)
        # You might need to adjust how consumption data is retrieved from aioaquarea
        entities.append(
            AquareaConsumptionSensor(
                coordinator,
                device_id,
                device,
                "daily_consumption",
                "Daily Consumption",
                UnitOfEnergy.KILO_WATT_HOUR,
                SensorDeviceClass.ENERGY,
                SensorStateClass.TOTAL_INCREASING,
                ConsumptionType.DAILY # Assuming daily consumption
            )
        )
    async_add_entities(entities)


class AquareaSensor(CoordinatorEntity[AquareaDataUpdateCoordinator], SensorEntity):
    """Representation of a Panasonic Aquarea sensor."""

    def __init__(
        self,
        coordinator: AquareaDataUpdateCoordinator,
        device_id: str,
        device: Device,
        sensor_type: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._sensor_type = sensor_type
        self._attr_name = f"Aquarea {device.info.name} {name}"
        self._attr_unique_id = f"{device.info.long_id}_{sensor_type}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self._sensor_type == "current_temperature":
            return self._device.status.current_temperature
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._device = self.coordinator.data.get(self._device_id, self._device)
        self.async_write_ha_state()

class AquareaConsumptionSensor(AquareaSensor):
    """Representation of a Panasonic Aquarea consumption sensor."""

    def __init__(
        self,
        coordinator: AquareaDataUpdateCoordinator,
        device_id: str,
        device: Device,
        sensor_type: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        consumption_type: ConsumptionType | None = None,
    ) -> None:
        """Initialize the consumption sensor."""
        super().__init__(
            coordinator, device_id, device, sensor_type, name, unit, device_class, state_class
        )
        self._consumption_type = consumption_type

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self._consumption_type:
            # Assuming consumption data is available directly on the device object
            # You might need to call a specific method on self._device to get consumption
            # For example: self._device.get_consumption(self._consumption_type)
            # For now, returning a placeholder or assuming it's part of status
            # This part needs to be aligned with how aioaquarea exposes consumption
            # For demonstration, let's assume a placeholder value
            # In a real scenario, you'd fetch this from the device object
            # For example, if device.status had a daily_consumption attribute:
            # return self._device.status.daily_consumption
            return None # Placeholder, needs actual implementation based on aioaquarea
        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        # If consumption data is part of the device object, it will be updated by super()
        # If it requires a separate call, that call should be part of the coordinator update
        # or handled here.
