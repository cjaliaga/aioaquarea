"""Statistics models for Aquarea"""

from __future__ import annotations

import math

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum


class DateType(StrEnum):
    """Date types"""

    DAY = "date"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class AggregationType(StrEnum):
    """Aggregation type"""

    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class ConsumptionType(StrEnum):
    """Data type"""

    HEAT = "Heat"
    COOL = "AC"
    WATER_TANK = "HW"
    TOTAL = "Consume"


def _sanitize_float(value: object) -> float | None:
    """Convert a value to float, handling NaN, None, and invalid values.

    :param value: The raw value from the API
    :return: float value or None if invalid
    """
    if value is None:
        return None
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (ValueError, TypeError):
        return None


class Consumption:
    """Consumption"""

    def __init__(self, data: dict[str, object]):
        self._data = data
        self._heat_consumption = _sanitize_float(data.get("heatConsumption"))
        self._cool_consumption = _sanitize_float(data.get("coolConsumption"))
        self._tank_consumption = _sanitize_float(data.get("tankConsumption"))
        self._heat_cost = _sanitize_float(data.get("heatCost"))
        self._cool_cost = _sanitize_float(data.get("coolCost"))
        self._tank_cost = _sanitize_float(data.get("tankCost"))
        self._data_time = data.get("dataTime")
        self._outdoor_temp = _sanitize_float(data.get("outdoorTemp"))

    @property
    def heat_consumption(self) -> float | None:
        """Heat consumption in kWh"""
        return self._heat_consumption

    @property
    def cool_consumption(self) -> float | None:
        """Cool consumption in kWh"""
        return self._cool_consumption

    @property
    def tank_consumption(self) -> float | None:
        """Tank consumption in kWh"""
        return self._tank_consumption

    @property
    def heat_cost(self) -> float | None:
        """Heat cost in configured currency"""
        return self._heat_cost

    @property
    def cool_cost(self) -> float | None:
        """Cool cost in configured currency"""
        return self._cool_cost

    @property
    def tank_cost(self) -> float | None:
        """Tank cost in configured currency"""
        return self._tank_cost

    @property
    def data_time(self) -> str | None:
        """Time of the data point"""
        return self._data_time

    @property
    def outdoor_temp(self) -> float | None:
        """Outdoor temperature"""
        return self._outdoor_temp

    @property
    def total_consumption(self) -> float | None:
        """Total consumption in kWh (sum of heat, cool, and tank consumption).

        Returns None only if all components are None (no data available).
        Returns 0 if all components are 0 (valid reading of zero consumption).
        """
        components = [
            self._heat_consumption,
            self._cool_consumption,
            self._tank_consumption,
        ]
        if all(c is None for c in components):
            return None
        return sum(c for c in components if c is not None)

    @property
    def raw_data(self) -> dict[str, object]:
        """Raw data from the API response"""
        return self._data
