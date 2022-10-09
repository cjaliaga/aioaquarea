"""Statistics models for Aquarea"""
from __future__ import annotations
from dataclasses import dataclass

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum


class AggregationType(StrEnum):
    """Aggregation type"""

    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class DataType(StrEnum):
    """Data type"""

    HEAT = "Heat"
    COOL = "AC"
    WATER_TANK = "HW"
    TOTAL = "Consume"


class DataSetName(StrEnum):
    ENERGY = "energyShowing"
    GENERATED = "generateEnergyShowing"
    COST = "costShowing"
    TEMPERATURE = "temperatureShowing"


class Consumption:
    @property
    def energy(self) -> float:
        """Energy consumption in kWh"""
        raise NotImplementedError

    @property
    def generation(self) -> float:
        """Energy generation in kWh"""
        raise NotImplementedError

    @property
    def cost(self) -> float:
        """Energy cost in configured currency"""
        raise NotImplementedError

    @property
    def start_date(self) -> str:
        """Start date of the period"""
        raise NotImplementedError

    @property
    def aggregation(self) -> AggregationType:
        """Aggregation type"""
        raise NotImplementedError
