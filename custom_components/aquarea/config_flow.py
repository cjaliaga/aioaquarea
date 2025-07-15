"""Config flow for Panasonic Aquarea integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
from aioaquarea import Client, AuthenticationError, ApiError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
    }
)

class AquareaConfigFlow(config_entries.ConfigFlow, domain="aquarea"):
    """Handle a config flow for Panasonic Aquarea."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                async with aiohttp.ClientSession() as session:
                    client = Client(
                        username=user_input["username"],
                        password=user_input["password"],
                        session=session,
                    )
                    # Attempt to get devices to verify credentials
                    await client.get_devices()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except ApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input["username"], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
