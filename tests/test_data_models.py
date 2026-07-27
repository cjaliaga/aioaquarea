"""Tests for aioaquarea data models."""

from aioaquarea.data import (
    Device,
    DeviceInfo,
    DeviceStatus,
    DeviceZone,
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
    TemperatureModifiers,
    ZoneSensor,
    ZoneTemperatureSetUpdate,
)


def test_device_zone_info_defaults():
    zone = DeviceZoneInfo(
        zone_id=1,
        name="Zone 1",
        type="Room",
        cool_mode=True,
        zone_sensor=ZoneSensor.INTERNAL,
        heat_sensor=SensorMode.DIRECT,
        cool_sensor=SensorMode.DIRECT,
    )
    assert zone.zone_id == 1
    assert zone.name == "Zone 1"
    assert zone.cool_mode is True


def test_device_zone_status_defaults():
    status = DeviceZoneStatus(
        zone_id=1,
        temperature=22,
        operation_status=OperationStatus.ON,
        heat_max=30,
        heat_min=15,
        heat_set=21,
        cool_max=28,
        cool_min=18,
        cool_set=24,
        comfort_heat=None,
        comfort_cool=None,
        eco_heat=None,
        eco_cool=None,
    )
    assert status.zone_id == 1
    assert status.temperature == 22
    assert status.operation_status == OperationStatus.ON
    assert status.heat_set == 21


def test_tank_status_defaults():
    tank = TankStatus(
        operation_status=OperationStatus.ON,
        temperature=45,
        heat_max=60,
        heat_min=30,
        heat_set=50,
    )
    assert tank.temperature == 45
    assert tank.heat_set == 50


def test_device_info_defaults():
    info = DeviceInfo(
        device_id="test-device-1",
        name="Test Device",
        long_id="test-long-id",
        mode=OperationMode.Heat,
        has_tank=True,
        firmware_version="1.0.0",
        model="WH-SDC12H9E3",
        zones=[],
        status_data_mode=StatusDataMode.LIVE,
    )
    assert info.device_id == "test-device-1"
    assert info.has_tank is True
    assert info.mode == OperationMode.Heat


def test_device_status_defaults():
    status = DeviceStatus(
        long_id="test-long-id",
        operation_status=OperationStatus.ON,
        device_status=0,
        temperature_outdoor=12,
        operation_mode=ExtendedOperationMode.HEAT,
        fault_status=[],
        direction=0,
        pump_duty=0,
        tank_status=[],
        zones=[],
        quiet_mode=QuietMode.OFF,
        force_dhw=ForceDHW.OFF,
        force_heater=ForceHeater.OFF,
        holiday_timer=HolidayTimer.OFF,
        powerful_time=PowerfulTime.OFF,
        special_status=None,
    )
    assert status.operation_status == OperationStatus.ON
    assert status.temperature_outdoor == 12
    assert status.operation_mode == ExtendedOperationMode.HEAT


def test_device_zone_construction():
    info = DeviceZoneInfo(
        zone_id=1,
        name="Living Room",
        type="Room",
        cool_mode=True,
        zone_sensor=ZoneSensor.INTERNAL,
        heat_sensor=SensorMode.DIRECT,
        cool_sensor=SensorMode.DIRECT,
    )
    status = DeviceZoneStatus(
        zone_id=1,
        temperature=22,
        operation_status=OperationStatus.ON,
        heat_max=30,
        heat_min=15,
        heat_set=21,
        cool_max=28,
        cool_min=18,
        cool_set=24,
        comfort_heat=None,
        comfort_cool=None,
        eco_heat=None,
        eco_cool=None,
    )
    zone = DeviceZone(info, status)
    assert zone.zone_id == 1
    assert zone.name == "Living Room"
    assert zone.temperature == 22
    assert zone.operation_status == OperationStatus.ON
    assert zone.heat_target_temperature == 21
    assert zone.cool_target_temperature == 24
    assert zone.heat_max == 30
    assert zone.heat_min == 15


def test_device_zone_supports_set_temperature():
    internal_info = DeviceZoneInfo(
        zone_id=1, name="Z1", type="Room", cool_mode=True,
        zone_sensor=ZoneSensor.INTERNAL,
        heat_sensor=SensorMode.DIRECT, cool_sensor=SensorMode.DIRECT,
    )
    external_info = DeviceZoneInfo(
        zone_id=2, name="Z2", type="Room", cool_mode=True,
        zone_sensor=ZoneSensor.EXTERNAL,
        heat_sensor=SensorMode.DIRECT, cool_sensor=SensorMode.DIRECT,
    )
    internal_zone = DeviceZone(internal_info, None)
    external_zone = DeviceZone(external_info, None)
    assert internal_zone.supports_set_temperature is True
    assert external_zone.supports_set_temperature is False
    assert internal_zone.supports_special_status is True
    assert external_zone.supports_special_status is False


def test_device_zone_external_sensor():
    info = DeviceZoneInfo(
        zone_id=1, name="Z1", type="Room", cool_mode=True,
        zone_sensor=ZoneSensor.EXTERNAL,
        heat_sensor=SensorMode.COMPENSATION_CURVE,
        cool_sensor=SensorMode.COMPENSATION_CURVE,
    )
    zone = DeviceZone(info, None)
    assert zone.sensor_mode == ZoneSensor.EXTERNAL
    assert zone.heat_sensor_mode == SensorMode.COMPENSATION_CURVE
    assert zone.cool_sensor_mode == SensorMode.COMPENSATION_CURVE


def test_temperature_modifiers():
    modifiers = TemperatureModifiers(heat=2, cool=-2)
    assert modifiers.heat == 2
    assert modifiers.cool == -2


def test_zone_temperature_set_update():
    update = ZoneTemperatureSetUpdate(zone_id=1, cool_set=25, heat_set=20)
    assert update.zone_id == 1
    assert update.heat_set == 20
    assert update.cool_set == 25


def test_fault_error():
    error = FaultError(error_message="Test error", error_code="1001-0001")
    assert error.error_message == "Test error"
    assert error.error_code == "1001-0001"


def test_special_status_enum():
    assert SpecialStatus.ECO == 1
    assert SpecialStatus.COMFORT == 2


def test_extended_operation_mode_values():
    assert ExtendedOperationMode.OFF == 0
    assert ExtendedOperationMode.HEAT == 1
    assert ExtendedOperationMode.COOL == 2
    assert ExtendedOperationMode.AUTO_HEAT == 3
    assert ExtendedOperationMode.AUTO_COOL == 4


def test_quiet_mode_values():
    assert QuietMode.OFF == 0
    assert QuietMode.LEVEL1 == 1
    assert QuietMode.LEVEL2 == 2
    assert QuietMode.LEVEL3 == 3
