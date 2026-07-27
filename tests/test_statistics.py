"""Tests for aioaquarea statistics models."""

import math

from aioaquarea.statistics import Consumption, DateType, ConsumptionType


class TestConsumption:
    def test_valid_data(self):
        c = Consumption({
            "heatConsumption": 15.5,
            "coolConsumption": 5.2,
            "tankConsumption": 3.1,
            "heatCost": 2.50,
            "coolCost": 0.80,
            "tankCost": 0.50,
            "dataTime": "20240101",
            "outdoorTemp": 12.0,
        })
        assert c.heat_consumption == 15.5
        assert c.cool_consumption == 5.2
        assert c.tank_consumption == 3.1
        assert c.total_consumption == 23.8
        assert c.heat_cost == 2.50
        assert c.cool_cost == 0.80
        assert c.tank_cost == 0.50
        assert c.data_time == "20240101"
        assert c.outdoor_temp == 12.0

    def test_nan_values(self):
        c = Consumption({
            "heatConsumption": float("nan"),
            "coolConsumption": "NaN",
            "tankConsumption": None,
        })
        assert c.heat_consumption is None
        assert c.cool_consumption is None
        assert c.tank_consumption is None
        assert c.total_consumption is None

    def test_inf_values(self):
        c = Consumption({
            "heatConsumption": float("inf"),
            "coolConsumption": float("-inf"),
        })
        assert c.heat_consumption is None
        assert c.cool_consumption is None

    def test_all_zeros(self):
        c = Consumption({
            "heatConsumption": 0,
            "coolConsumption": 0,
            "tankConsumption": 0,
        })
        assert c.total_consumption == 0

    def test_partial_data(self):
        c = Consumption({"heatConsumption": 8.0})
        assert c.heat_consumption == 8.0
        assert c.cool_consumption is None
        assert c.tank_consumption is None
        assert c.total_consumption == 8.0

    def test_empty_data(self):
        c = Consumption({})
        assert c.heat_consumption is None
        assert c.total_consumption is None
        assert c.data_time is None

    def test_invalid_types(self):
        c = Consumption({
            "heatConsumption": "invalid",
            "coolConsumption": [],
        })
        assert c.heat_consumption is None
        assert c.cool_consumption is None

    def test_string_numbers(self):
        c = Consumption({
            "heatConsumption": "10.5",
            "outdoorTemp": "25.0",
        })
        assert c.heat_consumption == 10.5
        assert c.outdoor_temp == 25.0

    def test_raw_data(self):
        raw = {"heatConsumption": 10}
        c = Consumption(raw)
        assert c.raw_data is raw


class TestEnums:
    def test_date_type(self):
        assert DateType.DAY == "date"
        assert DateType.WEEK == "week"
        assert DateType.MONTH == "month"
        assert DateType.YEAR == "year"

    def test_consumption_type(self):
        assert ConsumptionType.HEAT == "Heat"
        assert ConsumptionType.COOL == "AC"
        assert ConsumptionType.WATER_TANK == "HW"
        assert ConsumptionType.TOTAL == "Consume"
