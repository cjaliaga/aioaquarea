"""Support for Panasonic Aquarea climate."""
from __future__ import annotations

import logging
from typing import Any

from .aioaquarea import Device, UpdateOperationMode
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, AquareaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aquarea climate platform."""
    coordinator: AquareaDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    entities = []
    for device_id, device in coordinator.data.items():
        entities.append(AquareaClimate(coordinator, device_id, device))
    async_add_entities(entities)

class AquareaClimate(CoordinatorEntity[AquareaDataUpdateCoordinator], ClimateEntity):
    """Representation of a Panasonic Aquarea climate device."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF] # Only heat and off for now
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.HVAC_MODE
    )

    def __init__(
        self,
        coordinator: AquareaDataUpdateCoordinator,
        device_id: str,
        device: Device,
    ) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._attr_name = f"Aquarea {device.info.name}"
        self._attr_unique_id = f"{device.info.long_id}_climate"

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.status.current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we are trying to reach."""
        return self._device.status.target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation ie. heat, cool mode."""
        if self._device.status.operation_mode == UpdateOperationMode.OFF:
            return HVACMode.OFF
        return HVACMode.HEAT # Assuming HEAT for now

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._device.set_temperature(temperature, 1) # Assuming zone 1
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode."""
        if hvac_mode == HVACMode.HEAT:
            await self._device.set_mode(UpdateOperationMode.HEAT)
        elif hvac_mode == HVACMode.OFF:
            await self._device.set_mode(UpdateOperationMode.OFF)
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._device = self.coordinator.data.get(self._device_id, self._device)
        self.async_write_ha_state()
