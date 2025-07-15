"""Support for Panasonic Aquarea switches."""
from __future__ import annotations

from typing import Any

from .aioaquarea import Device, QuietMode, ForceDHW, ForceHeater
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, AquareaDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aquarea switch platform."""
    coordinator: AquareaDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    entities = []
    for device_id, device in coordinator.data.items():
        entities.append(
            AquareaSwitch(
                coordinator,
                device_id,
                device,
                "quiet_mode",
                "Quiet Mode",
                lambda d: d.status.quiet_mode == QuietMode.ON,
                lambda d, state: d.set_quiet_mode(QuietMode.ON if state else QuietMode.OFF),
            )
        )
        entities.append(
            AquareaSwitch(
                coordinator,
                device_id,
                device,
                "force_dhw",
                "Force DHW",
                lambda d: d.status.force_dhw == ForceDHW.ON,
                lambda d, state: d.set_force_dhw(ForceDHW.ON if state else ForceDHW.OFF),
            )
        )
        entities.append(
            AquareaSwitch(
                coordinator,
                device_id,
                device,
                "force_heater",
                "Force Heater",
                lambda d: d.status.force_heater == ForceHeater.ON,
                lambda d, state: d.set_force_heater(ForceHeater.ON if state else ForceHeater.OFF),
            )
        )
    async_add_entities(entities)


class AquareaSwitch(CoordinatorEntity[AquareaDataUpdateCoordinator], SwitchEntity):
    """Representation of a Panasonic Aquarea switch."""

    def __init__(
        self,
        coordinator: AquareaDataUpdateCoordinator,
        device_id: str,
        device: Device,
        switch_type: str,
        name: str,
        is_on_getter: callable,
        setter: callable,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._switch_type = switch_type
        self._is_on_getter = is_on_getter
        self._setter = setter
        self._attr_name = f"Aquarea {device.info.name} {name}"
        self._attr_unique_id = f"{device.info.long_id}_{switch_type}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        return self._is_on_getter(self._device)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._setter(self._device, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._setter(self._device, False)
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._device = self.coordinator.data.get(self._device_id, self._device)
        self.async_write_ha_state()
