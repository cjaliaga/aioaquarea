"""The Panasonic Aquarea integration."""
from __future__ import annotations

import logging
import asyncio
from datetime import timedelta

import aiohttp
from .aioaquarea import Client, Device, AuthenticationError, ApiError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.const import CONF_USERNAME
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import AquareaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

DOMAIN = "aquarea"
DEVICES = "devices" # Add DEVICES constant
PLATFORMS: list[str] = ["climate", "sensor", "switch", "water_heater", "binary_sensor", "button", "select"]

class AquareaBaseEntity(CoordinatorEntity[AquareaDataUpdateCoordinator]): # Change DataUpdateCoordinator to AquareaDataUpdateCoordinator
    """Base entity for Aquarea integration."""

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None: # Remove device parameter
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._device = coordinator.device # Get device from coordinator
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._device.device_id)}, # Use device_id
            "name": self._device.device_name, # Use device_name
            "manufacturer": self._device.manufacturer, # Use manufacturer
            "model": self._device.model, # Use model
            "sw_version": self._device.firmware_version, # Use firmware_version
        }

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return self._device.device_id

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Panasonic Aquarea from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data["password"]

    session = aiohttp.ClientSession()
    client = Client(username=username, password=password, session=session)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "session": session,
        DEVICES: {},
    }

    try:
        devices_info = await client.get_devices()
    except AuthenticationError as err:
        await session.close()
        raise ConfigEntryAuthFailed from err
    except ApiError as err:
        await session.close()
        raise ConfigEntryNotReady(f"Error communicating with API: {err}") from err
    except Exception as err:
        await session.close()
        raise ConfigEntryNotReady(f"Unexpected error: {err}") from err

    for device_info in devices_info:
        coordinator = AquareaDataUpdateCoordinator(hass, entry, client, device_info)
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id][DEVICES][device_info.device_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in data[DEVICES].values():
            await coordinator.async_shutdown()
        await data["session"].close()

    return unload_ok
