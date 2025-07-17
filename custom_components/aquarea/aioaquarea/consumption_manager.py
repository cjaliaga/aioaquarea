from __future__ import annotations

import logging # Added logging
import datetime as dt # Added datetime import
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

    def __init__(self, api_client: AquareaAPIClient, base_url: str, timezone: dt.timezone): # Added timezone
        self._api_client = api_client
        self._base_url = base_url
        self._timezone = timezone # Store timezone

    async def get_device_consumption(
        self, long_id: str, aggregation: DateType, date_input: str
    ) -> Consumption | None:
        """Get device consumption."""
        try:
            # Format timezone offset
            offset_seconds = self._timezone.utcoffset(dt.datetime.now()).total_seconds()
            offset_hours = int(offset_seconds / 3600)
            offset_minutes = int((offset_seconds % 3600) / 60)
            timezone_str = f"{offset_hours:+03d}:{offset_minutes:02d}"

            payload = {
                "apiName": "/remote/v1/api/consumption",
                "requestMethod": "POST",
                "bodyParam": {
                    "gwid": long_id,
                    "dataMode": int(aggregation.value),
                    "date": date_input,
                    "osTimezone": timezone_str, # Use dynamic timezone
                },
            }
            response = await self._api_client.request(
                "POST",
                url="remote/v1/app/common/transfer",
                json=payload,
                throw_on_error=True,
            )

            date_data = await response.json()
            _LOGGER.debug("Received consumption data: %s", date_data) # Added debug log
            if date_data and date_data.get("dateData"): # Check if dateData exists and is not empty
                _LOGGER.debug("Processing dateData: %s", date_data["dateData"][0]) # Added debug log
                return Consumption(date_data["dateData"][0])
            else:
                _LOGGER.warning(
                    "No consumption data found for device %s, date %s, aggregation %s. Full response: %s", # Modified warning
                    long_id,
                    date_input,
                    aggregation,
                    date_data, # Added full response to warning
                )
                return None
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
