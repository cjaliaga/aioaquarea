from __future__ import annotations

import logging # Added logging
from typing import TYPE_CHECKING

from .const import AQUAREA_SERVICE_A2W_STATUS_DISPLAY, AQUAREA_SERVICE_CONSUMPTION
from .statistics import Consumption, DateType # Import from statistics
from .auth import PanasonicRequestHeader
from .errors import ApiError, AuthenticationError # Import ApiError and AuthenticationError

if TYPE_CHECKING:
    from .api_client import AquareaAPIClient

_LOGGER = logging.getLogger(__name__) # Added logger

class AquareaConsumptionManager:
    """Handles consumption data retrieval."""

    def __init__(self, api_client: AquareaAPIClient, base_url: str):
        self._api_client = api_client
        self._base_url = base_url

    async def get_device_consumption(
        self, long_id: str, aggregation: DateType, date_input: str
    ) -> Consumption | None:
        """Get device consumption."""
        try:
            payload = {
                "apiName": "/remote/v1/api/consumption",
                "requestMethod": "POST",
                "bodyParam": {
                    "gwid": long_id,
                    "dataMode": int(aggregation.value),
                    "date": date_input,
                    "osTimezone": "+02:00", # Assuming a fixed timezone for now, might need to be dynamic
                },
            }
            response = await self._api_client.request(
                "POST",
                url="remote/v1/app/common/transfer",
                json=payload,
                throw_on_error=True,
            )

            date_data = await response.json()
            return Consumption(date_data.get("dateData")[0])
        except (ApiError, AuthenticationError) as ex:
            _LOGGER.warning(
                "Failed to get consumption data for device %s, date %s, aggregation %s: %s",
                long_id,
                date_input,
                aggregation,
                ex,
            )
            return None
        except Exception as ex:
            _LOGGER.exception(
                "An unexpected error occurred while getting consumption data for device %s, date %s, aggregation %s",
                long_id,
                date_input,
                aggregation,
            )
            return None
