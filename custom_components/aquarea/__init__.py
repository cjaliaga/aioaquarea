"""The Aquarea Smart Cloud integration."""
from __future__ import annotations
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aioaquarea import AquareaClient, AuthenticationError, ApiError, AuthenticationErrorCodes # Explicit import
from .const import ATTRIBUTION, CLIENT, DEVICES, DOMAIN
from .coordinator import AquareaDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.WATER_HEATER,
    Platform.SWITCH,
    Platform.SELECT
]

_LOGGER = logging.getLogger(__name__)

def _create_client(hass: HomeAssistant, entry: ConfigEntry) -> AquareaClient: # Use AquareaClient
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    session = async_create_clientsession(hass)
    return AquareaClient(session, username, password) # Use AquareaClient

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aquarea Smart Cloud from a config entry."""
    client = _create_client(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CLIENT: client,
        DEVICES: dict[str, AquareaDataUpdateCoordinator](),
    }

    try:
        await client.login()
        # Get all the devices, we will filter the disabled ones later
        devices = await client.get_devices(include_long_id=True)
        # We create a Coordinator per Device and store it in the hass.data[DOMAIN] dict to be able to access it from the platform
        for device in devices:
            coordinator = AquareaDataUpdateCoordinator(
                hass=hass, entry=entry, client=client, device_info=device
            )
            hass.data[DOMAIN][entry.entry_id][DEVICES][device.device_id] = coordinator
            await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except AuthenticationError as err: # Use AuthenticationError
        if err.error_code in (
            AuthenticationErrorCodes.INVALID_USERNAME_OR_PASSWORD, # Use AuthenticationErrorCodes
            AuthenticationErrorCodes.INVALID_CREDENTIALS, # Use AuthenticationErrorCodes
        ):
            raise ConfigEntryAuthFailed from err
        raise ConfigEntryNotReady(f"Authentication error: {err}") from err
    except ApiError as err: # Use ApiError
        raise ConfigEntryNotReady(f"Error communicating with API: {err}") from err
    except Exception as err:
        raise ConfigEntryNotReady(f"Unexpected error: {err}") from err

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in data[DEVICES].values():
            await coordinator.async_shutdown()
        await data[CLIENT].close() # Close the aiohttp session

    return unload_ok

class AquareaBaseEntity(CoordinatorEntity[AquareaDataUpdateCoordinator]):
    """Common base for Aquarea entities."""
    coordinator: AquareaDataUpdateCoordinator
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: AquareaDataUpdateCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._attrs: dict[str, Any] = {
            "name": self.coordinator.device.device_name,
            "id": self.coordinator.device.device_id,
        }
        self._attr_unique_id = self.coordinator.device.device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device.device_id)},
            manufacturer=self.coordinator.device.manufacturer,
            model=self.coordinator.device.model,
            name=self.coordinator.device.device_name,
            sw_version=self.coordinator.device.firmware_version,
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
