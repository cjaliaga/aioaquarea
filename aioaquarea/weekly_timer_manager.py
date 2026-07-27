import logging
from typing import TYPE_CHECKING

from .data import DayOfWeek, DaySchedule, WeeklyTimerSettings, WeeklyTimerSlot

if TYPE_CHECKING:
    from .api_client import AquareaAPIClient

_LOGGER = logging.getLogger(__name__)


class WeeklyTimerManager:
    """Handles weekly timer schedule retrieval and updates."""

    def __init__(self, api_client: "AquareaAPIClient", base_url: str):
        self._api_client = api_client
        self._base_url = base_url

    async def get_weekly_timer(self, device_id: str) -> WeeklyTimerSettings | None:
        """Retrieve the weekly timer schedule for a device.

        :param device_id: The device GUID
        :return: WeeklyTimerSettings if available, None otherwise
        """
        payload = {
            "apiName": "/remote/v1/api/weeklytimer",
            "requestMethod": "GET",
            "bodyParam": {"gwid": device_id},
        }

        response = await self._api_client.request(
            "POST",
            url="remote/v1/app/common/transfer",
            json=payload,
            throw_on_error=True,
        )

        data = await response.json()
        return self._parse_weekly_timer_response(data, device_id)

    async def set_weekly_timer(
        self, device_id: str, settings: WeeklyTimerSettings
    ) -> None:
        """Update the weekly timer schedule for a device.

        :param device_id: The device GUID
        :param settings: The weekly timer settings to apply
        """
        schedule_data = []
        for day_schedule in settings.schedule:
            for slot in day_schedule.slots:
                schedule_data.append(
                    {
                        "dayOfWeek": day_schedule.day.value,
                        "zoneId": slot.zone_id,
                        "startTime": f"{slot.start_hour:02d}:{slot.start_minute:02d}",
                        "endTime": f"{slot.end_hour:02d}:{slot.end_minute:02d}",
                        "heatSet": slot.heat_set,
                        "coolSet": slot.cool_set,
                        "enabled": slot.enabled,
                    }
                )

        payload = {
            "apiName": "/remote/v1/api/weeklytimer",
            "requestMethod": "POST",
            "bodyParam": {
                "gwid": device_id,
                "enabled": settings.enabled,
                "schedule": schedule_data,
            },
        }

        await self._api_client.request(
            "POST",
            url="remote/v1/app/common/transfer",
            json=payload,
            throw_on_error=True,
        )

    def _parse_weekly_timer_response(
        self, data: dict, device_id: str
    ) -> WeeklyTimerSettings | None:
        """Parse the weekly timer response from the API.

        :param data: The JSON response from the API
        :param device_id: The device GUID for logging
        :return: WeeklyTimerSettings if data is valid, None otherwise
        """
        if not data or "schedule" not in data:
            _LOGGER.warning(
                "No weekly timer data found for device %s. Response: %s",
                device_id,
                data,
            )
            return None

        enabled = data.get("enabled", False)
        raw_schedule = data.get("schedule", [])

        day_map: dict[int, list[WeeklyTimerSlot]] = {}

        for entry in raw_schedule:
            day_value = entry.get("dayOfWeek")
            if day_value is None:
                continue

            try:
                day = DayOfWeek(day_value)
            except ValueError:
                _LOGGER.warning("Unknown day of week: %s", day_value)
                continue

            start_str = entry.get("startTime", "00:00")
            end_str = entry.get("endTime", "00:00")

            try:
                start_hour, start_minute = map(int, start_str.split(":"))
                end_hour, end_minute = map(int, end_str.split(":"))
            except (ValueError, AttributeError):
                _LOGGER.warning("Invalid time format in weekly timer: %s, %s", start_str, end_str)
                continue

            slot = WeeklyTimerSlot(
                zone_id=entry.get("zoneId", 1),
                start_hour=start_hour,
                start_minute=start_minute,
                end_hour=end_hour,
                end_minute=end_minute,
                heat_set=entry.get("heatSet"),
                cool_set=entry.get("coolSet"),
                enabled=entry.get("enabled", True),
            )

            if day.value not in day_map:
                day_map[day.value] = []
            day_map[day.value].append(slot)

        schedule = [
            DaySchedule(day=DayOfWeek(day_value), slots=slots)
            for day_value, slots in sorted(day_map.items())
        ]

        return WeeklyTimerSettings(enabled=enabled, schedule=schedule)
