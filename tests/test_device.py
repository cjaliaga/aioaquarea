"""Tests for Device class business logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aioaquarea.data import (
    DeviceAction,
    DeviceDirection,
    DeviceInfo,
    DeviceModeStatus,
    DeviceStatus,
    DeviceZoneInfo,
    DeviceZoneStatus,
    ExtendedOperationMode,
    FaultError,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    OperationMode,
    OperationStatus,
    PowerfulTime,
    QuietMode,
    SensorMode,
    SpecialStatus,
    StatusDataMode,
    TankStatus,
    ZoneSensor,
)
from aioaquarea.entities import DeviceImpl


def make_device_info(
    device_id="test-device",
    has_tank=False,
    zones=None,
):
    if zones is None:
        zones = []
    return DeviceInfo(
        device_id=device_id,
        name="Test Device",
        long_id=device_id,
        mode=OperationMode.Heat,
        has_tank=has_tank,
        firmware_version="1.0.0",
        model="WH-SDC12H9E3",
        zones=zones,
        status_data_mode=StatusDataMode.LIVE,
    )


def make_zone_status(
    zone_id=1,
    temperature=22,
    op_status=OperationStatus.ON,
    heat_max=30,
    heat_min=15,
    heat_set=21,
    cool_max=28,
    cool_min=18,
    cool_set=24,
):
    return DeviceZoneStatus(
        zone_id=zone_id,
        temperature=temperature,
        operation_status=op_status,
        heat_max=heat_max,
        heat_min=heat_min,
        heat_set=heat_set,
        cool_max=cool_max,
        cool_min=cool_min,
        cool_set=cool_set,
        comfort_heat=None,
        comfort_cool=None,
        eco_heat=None,
        eco_cool=None,
    )


def make_device_status(
    zones=None,
    operation_status=OperationStatus.ON,
    operation_mode=ExtendedOperationMode.HEAT,
    tank_status=None,
    **kwargs,
):
    if zones is None:
        zones = []
    if tank_status is None:
        tank_status = []
    return DeviceStatus(
        long_id="test-device",
        operation_status=operation_status,
        device_status=0,
        temperature_outdoor=12,
        operation_mode=operation_mode,
        fault_status=[],
        direction=0,
        pump_duty=0,
        tank_status=tank_status,
        zones=zones,
        quiet_mode=kwargs.get("quiet_mode", QuietMode.OFF),
        force_dhw=kwargs.get("force_dhw", ForceDHW.OFF),
        force_heater=kwargs.get("force_heater", ForceHeater.OFF),
        holiday_timer=kwargs.get("holiday_timer", HolidayTimer.OFF),
        powerful_time=kwargs.get("powerful_time", PowerfulTime.OFF),
        special_status=None,
    )


@pytest.fixture
def device_with_zones():
    zone_info = DeviceZoneInfo(
        zone_id=1, name="Zone 1", type="Room", cool_mode=True,
        zone_sensor=ZoneSensor.INTERNAL,
        heat_sensor=SensorMode.DIRECT, cool_sensor=SensorMode.DIRECT,
    )
    zone_status = make_zone_status()
    device_status = make_device_status(zones=[zone_status])
    client = MagicMock()
    client.post_device_operation_update = AsyncMock()
    client.post_device_operation_status = AsyncMock()
    client.post_device_set_quiet_mode = AsyncMock()
    client.post_device_force_dhw = AsyncMock()
    client.post_device_force_heater = AsyncMock()
    client.post_device_set_powerful_time = AsyncMock()
    client.post_device_holiday_timer = AsyncMock()
    client.post_device_request_defrost = AsyncMock()
    client.post_device_zone_heat_temperature = AsyncMock()
    client.post_device_zone_cool_temperature = AsyncMock()
    client.post_device_set_special_status = AsyncMock()
    client._post_device_batch_update = AsyncMock()

    device = DeviceImpl(
        device_id="test-device",
        long_id="test-device",
        name="Test Device",
        firmware_version="1.0.0",
        model="WH-SDC12H9E3",
        has_tank=False,
        zones_info=[zone_info],
        status=device_status,
        client=client,
    )
    return device, client


class TestDeviceProperties:
    def test_basic_properties(self, device_with_zones):
        device, _ = device_with_zones
        assert device.device_name == "Test Device"
        assert device.device_id == "test-device"
        assert device.long_id == "test-device"
        assert device.model == "WH-SDC12H9E3"
        assert device.firmware_version == "1.0.0"
        assert device.manufacturer == "Panasonic"
        assert device.has_tank is False
        assert device.tank is None

    def test_operation_properties(self, device_with_zones):
        device, _ = device_with_zones
        assert device.operation_status == OperationStatus.ON
        assert device.mode == ExtendedOperationMode.HEAT
        assert device.temperature_outdoor == 12

    def test_zones_property(self, device_with_zones):
        device, _ = device_with_zones
        assert len(device.zones) == 1
        assert 1 in device.zones
        assert device.zones[1].zone_id == 1

    def test_heat_max(self, device_with_zones):
        device, _ = device_with_zones
        assert device.heat_max == 30

    def test_cool_max(self, device_with_zones):
        device, _ = device_with_zones
        assert device.cool_max == 28

    def test_support_cooling(self, device_with_zones):
        device, _ = device_with_zones
        assert device.support_cooling() is True
        assert device.support_cooling(zone_id=1) is True

    def test_current_action_heating(self, device_with_zones):
        device, _ = device_with_zones
        # Status has direction=0 (IDLE), operation_status=ON, mode=HEAT
        # With direction=IDLE, current_action should be IDLE
        assert device.current_action == DeviceAction.IDLE

    def test_current_action_off(self, device_with_zones):
        device, client = device_with_zones
        # Create a device with OFF operation status
        off_status = make_device_status(
            operation_status=OperationStatus.OFF,
            zones=[make_zone_status(op_status=OperationStatus.OFF)],
        )
        device._status = off_status
        assert device.current_action == DeviceAction.OFF

    def test_is_on_error(self, device_with_zones):
        device, _ = device_with_zones
        assert device.is_on_error is False
        assert device.current_error is None

    def test_error_state(self, device_with_zones):
        device, client = device_with_zones
        error_status = make_device_status(
            zones=[make_zone_status()],
        )
        error_status.fault_status = [
            FaultError(error_message="Test error", error_code="1001-0001")
        ]
        device._status = error_status
        assert device.is_on_error is True
        assert device.current_error is not None
        assert device.current_error.error_message == "Test error"


class TestDeviceControl:
    @pytest.mark.asyncio
    async def test_turn_on(self, device_with_zones):
        device, client = device_with_zones
        off_status = make_device_status(
            operation_status=OperationStatus.OFF,
            zones=[make_zone_status(op_status=OperationStatus.OFF)],
        )
        device._status = off_status
        await device.turn_on()
        client.post_device_operation_status.assert_awaited_once_with(
            "test-device", OperationStatus.ON
        )

    @pytest.mark.asyncio
    async def test_turn_off(self, device_with_zones):
        device, client = device_with_zones
        await device.turn_off()
        client.post_device_operation_status.assert_awaited_once_with(
            "test-device", OperationStatus.OFF
        )

    @pytest.mark.asyncio
    async def test_set_mode_heat(self, device_with_zones):
        device, client = device_with_zones
        from aioaquarea import UpdateOperationMode

        await device.set_mode(UpdateOperationMode.HEAT)
        client.post_device_operation_update.assert_awaited_once()
        args = client.post_device_operation_update.call_args[0]
        assert args[1] == UpdateOperationMode.HEAT

    @pytest.mark.asyncio
    async def test_set_mode_off(self, device_with_zones):
        device, client = device_with_zones
        from aioaquarea import UpdateOperationMode

        await device.set_mode(UpdateOperationMode.OFF)
        client.post_device_operation_update.assert_awaited_once()
        args = client.post_device_operation_update.call_args[0]
        assert args[1] == UpdateOperationMode.OFF

    @pytest.mark.asyncio
    async def test_set_temperature_heat(self, device_with_zones):
        device, client = device_with_zones
        await device.set_temperature(23, zone_id=1)
        client.post_device_zone_heat_temperature.assert_awaited_once_with(
            "test-device", 1, 23
        )

    @pytest.mark.asyncio
    async def test_set_quiet_mode(self, device_with_zones):
        device, client = device_with_zones
        await device.set_quiet_mode(QuietMode.LEVEL1)
        client.post_device_set_quiet_mode.assert_awaited_once_with(
            "test-device", QuietMode.LEVEL1
        )


class TestDeviceWithTank:
    @pytest.fixture
    def device_with_tank(self):
        zone_info = DeviceZoneInfo(
            zone_id=1, name="Zone 1", type="Room", cool_mode=True,
            zone_sensor=ZoneSensor.INTERNAL,
            heat_sensor=SensorMode.DIRECT, cool_sensor=SensorMode.DIRECT,
        )
        zone_status = make_zone_status()
        tank_status = TankStatus(
            operation_status=OperationStatus.ON,
            temperature=45,
            heat_max=60,
            heat_min=30,
            heat_set=50,
        )
        device_status = make_device_status(
            zones=[zone_status],
            tank_status=[tank_status],
        )
        client = MagicMock()
        client.post_device_tank_temperature = AsyncMock()
        client.post_device_tank_operation_status = AsyncMock()
        client.post_device_force_dhw = AsyncMock()
        client.post_device_force_heater = AsyncMock()
        client._post_device_batch_update = AsyncMock()

        device = DeviceImpl(
            device_id="test-device",
            long_id="test-device",
            name="Test Device",
            firmware_version="1.0.0",
            model="WH-SDC12H9E3",
            has_tank=True,
            zones_info=[zone_info],
            status=device_status,
            client=client,
        )
        return device, client

    def test_tank_properties(self, device_with_tank):
        device, _ = device_with_tank
        assert device.has_tank is True
        assert device.tank is not None
        assert device.tank.temperature == 45
        assert device.tank.target_temperature == 50
        assert device.tank.operation_status == OperationStatus.ON
        assert device.tank.heat_min == 30
        assert device.tank.heat_max == 60


class TestSpecialStatus:
    @pytest.fixture
    def device_with_special_status(self):
        zone_info = DeviceZoneInfo(
            zone_id=1, name="Zone 1", type="Room", cool_mode=True,
            zone_sensor=ZoneSensor.INTERNAL,
            heat_sensor=SensorMode.DIRECT, cool_sensor=SensorMode.DIRECT,
        )
        zone_status = DeviceZoneStatus(
            zone_id=1, temperature=22, operation_status=OperationStatus.ON,
            heat_max=30, heat_min=15, heat_set=21,
            cool_max=28, cool_min=18, cool_set=24,
            comfort_heat=2, comfort_cool=-2, eco_heat=-2, eco_cool=2,
        )
        device_status = make_device_status(zones=[zone_status])
        client = MagicMock()
        client.post_device_set_special_status = AsyncMock()
        client._post_device_batch_update = AsyncMock()
        device = DeviceImpl(
            device_id="test-device", long_id="test-device",
            name="Test Device", firmware_version="1.0.0",
            model="WH-SDC12H9E3", has_tank=False,
            zones_info=[zone_info], status=device_status, client=client,
        )
        return device, client

    @pytest.mark.asyncio
    async def test_set_special_status_eco(self, device_with_special_status):
        device, client = device_with_special_status
        await device.set_special_status(SpecialStatus.ECO)
        client.post_device_set_special_status.assert_awaited_once()
        args = client.post_device_set_special_status.call_args[0]
        assert args[1] == SpecialStatus.ECO

    @pytest.mark.asyncio
    async def test_set_special_status_none(self, device_with_zones):
        device, client = device_with_zones
        # Setting to None when already None should be a no-op
        await device.set_special_status(None)
        client.post_device_set_special_status.assert_not_called()


class TestErrorHandling:
    def test_no_errors(self, device_with_zones):
        device, _ = device_with_zones
        assert device.is_on_error is False
        assert device.current_error is None

    def test_with_errors(self, device_with_zones):
        device, client = device_with_zones
        error_status = make_device_status(
            zones=[make_zone_status()],
        )
        error_status.fault_status = [
            FaultError(error_message="Communication error", error_code="1001-0001")
        ]
        device._status = error_status
        assert device.is_on_error is True
        assert device.current_error.error_message == "Communication error"
        assert str(device.current_error.error_code) == "1001-0001"
