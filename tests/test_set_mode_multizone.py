"""Regression tests for DeviceImpl.set_mode() with multiple zones.

Background
----------
`set_mode()` builds a per-zone `OperationStatus` dict AND sends a single,
device-wide `operationMode` field to the API. Historically that field was
always set to whatever `mode` the *caller* passed in - even when the call
was only meant to switch a single zone off while another zone stayed
active. Turning zone 2 off (via its own climate entity) sent
`operationMode: OFF` to the API while zone 1's entry in the `zoneStatus`
array was still `ON`, which desyncs the physical unit (see
wpatrik14/home-assistant-aquarea#25 for the reported symptoms: turning one
zone off puts the whole heat pump into water-heating-only mode, and the
heat pump's own display disagrees with Home Assistant afterwards).

`operationMode` should only be OFF when the whole device (every zone, and
the tank if present) is actually being shut down. Otherwise it must keep
reporting the device's current heat/cool/auto mode.

Run with:

    venv/bin/python -m pytest tests/test_set_mode_multizone.py -v
"""
import asyncio

import pytest

from aioaquarea.data import (
    DeviceInfo,
    DeviceStatus,
    DeviceZoneInfo,
    DeviceZoneStatus,
    DeviceModeStatus,
    DeviceDirection,
    ExtendedOperationMode,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    OperationMode,
    OperationStatus,
    PowerfulTime,
    PumpDuty,
    QuietMode,
    SensorMode,
    SpecialStatus,
    StatusDataMode,
    UpdateOperationMode,
    ZoneSensor,
    ZoneType,
)
from aioaquarea.entities import DeviceImpl


def _zone_info(zone_id: int) -> DeviceZoneInfo:
    return DeviceZoneInfo(
        zone_id=zone_id,
        name=f"Zone {zone_id}",
        type=ZoneType.ROOM,
        cool_mode=False,
        zone_sensor=ZoneSensor.INTERNAL,
        heat_sensor=SensorMode.DIRECT,
        cool_sensor=None,
    )


def _zone_status(zone_id: int, status: OperationStatus) -> DeviceZoneStatus:
    return DeviceZoneStatus(
        zone_id=zone_id,
        temperature=21,
        operation_status=status,
        heat_max=30,
        heat_min=15,
        heat_set=22,
        cool_max=None,
        cool_min=None,
        cool_set=None,
        comfort_heat=None,
        comfort_cool=None,
        eco_heat=None,
        eco_cool=None,
    )


class _FakeClient:
    """Captures the arguments passed to post_device_operation_update."""

    def __init__(self):
        self.calls = []

    async def post_device_operation_update(
        self,
        long_id,
        mode,
        zones,
        operation_status,
        tank_operation_status,
        zone_temperature_updates=None,
    ):
        self.calls.append(
            {
                "mode": mode,
                "zones": dict(zones),
                "operation_status": operation_status,
                "tank_operation_status": tank_operation_status,
            }
        )


def _make_two_zone_device(client: _FakeClient) -> DeviceImpl:
    zones_info = [_zone_info(1), _zone_info(2)]
    status = DeviceStatus(
        long_id="long-1",
        operation_status=OperationStatus.ON,
        device_status=DeviceModeStatus.NORMAL,
        temperature_outdoor=10,
        operation_mode=ExtendedOperationMode.HEAT,
        fault_status=[],
        direction=DeviceDirection.PUMP,
        pump_duty=PumpDuty.ON,
        tank_status=[],
        zones=[
            _zone_status(1, OperationStatus.ON),
            _zone_status(2, OperationStatus.ON),
        ],
        quiet_mode=QuietMode.OFF,
        force_dhw=ForceDHW.OFF,
        force_heater=ForceHeater.OFF,
        holiday_timer=HolidayTimer.OFF,
        powerful_time=PowerfulTime.OFF,
        special_status=None,
    )
    device = DeviceImpl(
        device_id="dev-1",
        long_id="long-1",
        name="Test device",
        firmware_version="1.0",
        model="Test model",
        has_tank=False,
        zones_info=zones_info,
        status=status,
        client=client,
    )
    return device


def test_turning_off_one_zone_keeps_device_mode_for_other_active_zone():
    """Zone 2 off, zone 1 still on -> operationMode must stay HEAT, not OFF."""
    client = _FakeClient()
    device = _make_two_zone_device(client)

    asyncio.run(device.set_mode(UpdateOperationMode.OFF, zone_id=2))

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["zones"][1] == OperationStatus.ON
    assert call["zones"][2] == OperationStatus.OFF
    assert call["operation_status"] == OperationStatus.ON
    assert call["mode"] == UpdateOperationMode.HEAT, (
        f"expected operationMode to stay HEAT while zone 1 is still on, "
        f"got {call['mode']!r}"
    )


def test_turning_off_the_last_active_zone_sends_off():
    """Turning off the only remaining active zone -> operationMode OFF is correct."""
    client = _FakeClient()
    device = _make_two_zone_device(client)
    # Zone 1 already off, only zone 2 is active.
    device.zones[1]._status.operation_status = OperationStatus.OFF

    asyncio.run(device.set_mode(UpdateOperationMode.OFF, zone_id=2))

    call = client.calls[0]
    assert call["zones"][1] == OperationStatus.OFF
    assert call["zones"][2] == OperationStatus.OFF
    assert call["operation_status"] == OperationStatus.OFF
    assert call["mode"] == UpdateOperationMode.OFF


def test_turning_on_a_zone_still_sends_requested_mode():
    """Sanity check: the non-OFF path is unaffected by the fix."""
    client = _FakeClient()
    device = _make_two_zone_device(client)

    asyncio.run(device.set_mode(UpdateOperationMode.COOL, zone_id=1))

    call = client.calls[0]
    assert call["mode"] == UpdateOperationMode.COOL


if __name__ == "__main__":
    test_turning_off_one_zone_keeps_device_mode_for_other_active_zone()
    test_turning_off_the_last_active_zone_sends_off()
    test_turning_on_a_zone_still_sends_requested_mode()
    print("ALL PASSED")
