"""Buttons for Aquarea integration."""
import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .aioaquarea import DeviceModeStatus, ForceDHW, ForceHeater, HolidayTimer
from . import AquareaBaseEntity
from .const import DEVICES, DOMAIN
from .coordinator import AquareaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aquarea buttons from config entry."""
    data: dict[str, AquareaDataUpdateCoordinator] = hass.data[DOMAIN][
        config_entry.entry_id
    ][DEVICES]
    entities: list[ButtonEntity] = []
    entities.extend([AquareaDefrostButton(coordinator) for coordinator in data.values()])
    entities.extend(
        [
            AquareaForceDHWButton(coordinator)
            for coordinator in data.values()
            if coordinator.device.has_tank
        ]
    )
    entities.extend([AquareaForceHeaterButton(coordinator) for coordinator in data.values()])
    entities.extend([AquareaHolidayTimerButton(coordinator) for coordinator in data.values()])
    async_add_entities(entities)

class AquareaDefrostButton(AquareaBaseEntity, ButtonEntity):
    """Representation of a Aquarea button that request the device to start the defrost process."""
    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{super().unique_id}_request_defrost"
        self._attr_name = "Request Defrost"
        self._attr_translation_key = "request_defrost"
        self._attr_icon = "mdi:snowflake-melt"

    async def async_press(self) -> None:
        """Request to start the defrost process."""
        if self.coordinator.device.device_mode_status is not DeviceModeStatus.DEFROST:
            _LOGGER.debug(
                "Requesting defrost for device %s",
                self.coordinator.device.device_name,
            )
            await self.coordinator.device.request_defrost()

class AquareaForceDHWButton(AquareaBaseEntity, ButtonEntity):
    """Representation of a Aquarea button that forces DHW mode."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{super().unique_id}_force_dhw"
        self._attr_name = "Force DHW"
        self._attr_translation_key = "force_dhw"
        self._attr_icon = "mdi:water-boiler"

    async def async_press(self) -> None:
        """Toggle Force DHW mode."""
        current = self.coordinator.device.force_dhw
        new_state = ForceDHW.OFF if current is ForceDHW.ON else ForceDHW.ON
        await self.coordinator.device.set_force_dhw(new_state)

class AquareaForceHeaterButton(AquareaBaseEntity, ButtonEntity):
    """Representation of a Aquarea button that forces heater mode."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{super().unique_id}_force_heater"
        self._attr_name = "Force Heating"
        self._attr_translation_key = "force_heater"
        self._attr_icon = "mdi:hvac"

    async def async_press(self) -> None:
        """Toggle Force heater mode."""
        current = self.coordinator.device.force_heater
        new_state = ForceHeater.OFF if current is ForceHeater.ON else ForceHeater.ON
        await self.coordinator.device.set_force_heater(new_state)

class AquareaHolidayTimerButton(AquareaBaseEntity, ButtonEntity):
    """Representation of a Aquarea button that toggles holiday timer."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{super().unique_id}_holiday_timer"
        self._attr_name = "Holiday Timer"
        self._attr_translation_key = "holiday_timer"
        self._attr_icon = "mdi:timer"

    async def async_press(self) -> None:
        """Toggle Holiday Timer mode."""
        current = self.coordinator.device.holiday_timer
        new_state = HolidayTimer.OFF if current is HolidayTimer.ON else HolidayTimer.ON
        await self.coordinator.device.set_holiday_timer(new_state)
