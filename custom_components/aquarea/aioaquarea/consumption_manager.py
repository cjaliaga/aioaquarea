from __future__ import annotations

import logging
import datetime as dt
from typing import TYPE_CHECKING

from .const import AQUAREA_SERVICE_A2W_STATUS_DISPLAY, AQUAREA_SERVICE_CONSUMPTION
from .statistics import Consumption, DateType
from .auth import PanasonicRequestHeader
from .errors import ApiError, AuthenticationError

if TYPE_CHECKING:
    from .api_client import AquareaAPIClient

_LOGGER = logging.getLogger(__name__)

class AquareaConsumptionManager:
    """Handles consumption data retrieval."""

    def __init__(self, api_client: AquareaAPIClient, base_url: str, timezone: dt.timezone):
        self._api_client = api_client
        self._base_url = base_url
        self._timezone = timezone

    async def get_device_consumption(
        self, long_id: str, aggregation: DateType, date_input: str
    ) -> list[Consumption] | None:
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
                    "osTimezone": timezone_str,
                },
            }
            response = await self._api_client.request(
                "POST",
                url="remote/v1/app/common/transfer",
                json=payload,
                throw_on_error=True,
            )

            consumption_data = await response.json()
            _LOGGER.debug("Received consumption data: %s", consumption_data)
            if consumption_data and consumption_data.get("historyDataList"):
                _LOGGER.debug("Processing historyDataList: %s", consumption_data["historyDataList"])
                return [Consumption(item) for item in consumption_data["historyDataList"]]
            else:
                _LOGGER.warning(
                    "No consumption data found for device %s, date %s, aggregation %s. Full response: %s",
                    long_id,
                    date_input,
                    aggregation,
                    consumption_data,
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
