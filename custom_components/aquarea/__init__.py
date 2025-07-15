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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed, CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

DOMAIN = "aquarea"
PLATFORMS: list[str] = ["climate", "sensor", "switch", "water_heater"]

class AquareaBaseEntity(CoordinatorEntity[DataUpdateCoordinator]):
    """Base entity for Aquarea integration."""

    def __init__(self, coordinator: DataUpdateCoordinator, device: Device) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._device._info.long_id)},
            "name": self._device._info.name,
            "manufacturer": self._device._info.manufacturer,
            "model": "Aquarea Heat Pump", # Generic model name
            "sw_version": self._device._info.firmware_version,
        }

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return self._device._info.long_id

class AquareaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Device]]):
    """Class to manage fetching Aquarea data."""

    def __init__(self, hass: HomeAssistant, client: Client) -> None:
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5), # Poll every 5 minutes
        )

    async def _async_update_data(self) -> dict[str, Device]:
        """Update data via library."""
        try:
            devices_info = await self.client.get_devices()
            devices = {}
            for device_info in devices_info:
                device = await self.client.get_device(device_info=device_info)
                devices[device._info.long_id] = device
            return devices
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Panasonic Aquarea from a config entry."""
    username = entry.data["username"]
    password = entry.data["password"]

    session = aiohttp.ClientSession()
    client = Client(username=username, password=password, session=session)

    try:
        coordinator = AquareaDataUpdateCoordinator(hass, client)
        await coordinator.async_config_entry_first_refresh()
    except (AuthenticationError, ApiError) as ex:
        _LOGGER.error("Failed to set up Aquarea integration: %s", ex)
        await session.close()
        raise ConfigEntryAuthFailed from ex
    except Exception as ex:
        _LOGGER.error("Unexpected error during Aquarea setup: %s", ex)
        await session.close()
        raise ConfigEntryNotReady from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "session": session, # Store session to close later
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["session"].close() # Close the aiohttp session

    return unload_ok
