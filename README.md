Aioaquarea
===================

Asynchronous library to control Panasonic Aquarea devices via the Panasonic Comfort Cloud API.

## Requirements

- Python >= 3.9
- `aiohttp`
- `beautifulsoup4` (bs4)

## Installation

```bash
pip install aioaquarea
```

## Quick Start

```python
from aioaquarea import Client, AquareaEnvironment, UpdateOperationMode
import aiohttp
import asyncio
from datetime import timedelta

async def main():
    async with aiohttp.ClientSession() as session:
        client = Client(
            username="YOUR_EMAIL",
            password="YOUR_PASSWORD",
            session=session,
            environment=AquareaEnvironment.PRODUCTION,
        )

        # Get all devices on the account
        devices = await client.get_devices()
        device_info = devices[0]

        # Get a device with automatic consumption data refresh
        device = await client.get_device(
            device_info=device_info,
            consumption_refresh_interval=timedelta(minutes=5),
        )

        print(f"Device: {device.device_name} ({device.model})")
        print(f"Mode: {device.mode.name}")
        print(f"Outdoor temperature: {device.temperature_outdoor}°C")

        # Change operation mode
        await device.set_mode(UpdateOperationMode.HEAT)

        # Refresh device data
        await device.refresh_data()

        await client.close()

asyncio.run(main())
```

## Features

### Device Information

```python
# Basic info
device.device_name       # "My Heat Pump"
device.model             # "WH-SDC12H9E3"
device.firmware_version  # "1.23"
device.has_tank          # True/False
device.long_id           # Device GUID

# Status
device.operation_status  # OperationStatus.ON / OFF
device.mode              # ExtendedOperationMode.HEAT / COOL / OFF / AUTO_HEAT / AUTO_COOL
device.temperature_outdoor  # Outdoor temperature in °C
device.current_action    # DeviceAction.HEATING / COOLING / HEATING_WATER / IDLE / OFF
device.current_direction # DeviceDirection.IDLE / PUMP / WATER

# Errors
device.is_on_error       # True if device has active errors
device.current_error     # FaultError or None
```

### Zone Control

Devices expose one or more zones, accessed via `device.zones` (a dict keyed by zone ID):

```python
for zone_id, zone in device.zones.items():
    print(f"Zone {zone_id}: {zone.temperature}°C, target heat={zone.heat_target_temperature}°C")

# Set temperature for a specific zone
await device.set_temperature(21, zone_id=1)
```

### Tank (Domestic Hot Water)

If the device has a tank, it is accessible via `device.tank`:

```python
if device.has_tank and device.tank:
    tank = device.tank
    print(f"Tank temp: {tank.temperature}°C, target: {tank.target_temperature}°C")
    print(f"Min: {tank.heat_min}°C, Max: {tank.heat_max}°C")

    # Set target temperature
    await tank.set_target_temperature(50)

    # Turn on/off
    await tank.turn_on()
    await tank.turn_off()
```

### Operation Mode

```python
from aioaquarea import UpdateOperationMode

# Switch mode
await device.set_mode(UpdateOperationMode.HEAT)
await device.set_mode(UpdateOperationMode.COOL)
await device.set_mode(UpdateOperationMode.OFF)
await device.set_mode(UpdateOperationMode.AUTO)

# Turn on/off the whole device
await device.turn_on()
await device.turn_off()
```

### Special Status (Eco / Comfort)

```python
from aioaquarea import SpecialStatus

# Check if the device supports special status modes
if device.support_special_status:
    await device.set_special_status(SpecialStatus.ECO)      # Energy-saving mode
    await device.set_special_status(SpecialStatus.COMFORT)  # Comfort mode
    await device.set_special_status(None)                    # Reset to normal
```

### Quiet Mode

```python
from aioaquarea import QuietMode

await device.set_quiet_mode(QuietMode.LEVEL1)  # Quiet
await device.set_quiet_mode(QuietMode.LEVEL2)  # Quieter
await device.set_quiet_mode(QuietMode.LEVEL3)  # Quietest
await device.set_quiet_mode(QuietMode.OFF)     # Normal
```

### Force DHW & Force Heater

```python
from aioaquarea import ForceDHW, ForceHeater

# Force domestic hot water heating
await device.set_force_dhw(ForceDHW.ON)
await device.set_force_dhw(ForceDHW.OFF)

# Force heater operation
await device.set_force_heater(ForceHeater.ON)
await device.set_force_heater(ForceHeater.OFF)
```

### Holiday Timer

```python
from aioaquarea import HolidayTimer

await device.set_holiday_timer(HolidayTimer.ON)
await device.set_holiday_timer(HolidayTimer.OFF)
```

### Powerful Time

```python
from aioaquarea import PowerfulTime

await device.set_powerful_time(PowerfulTime.ON_30MIN)
await device.set_powerful_time(PowerfulTime.ON_60MIN)
await device.set_powerful_time(PowerfulTime.ON_90MIN)
await device.set_powerful_time(PowerfulTime.OFF)
```

### Defrost

```python
await device.request_defrost()
```

### Weekly Timer

```python
from aioaquarea import DayOfWeek, WeeklyTimerSlot, DaySchedule, WeeklyTimerSettings

# Read the current schedule
settings = await device.get_weekly_timer()
if settings:
    print(f"Weekly timer enabled: {settings.enabled}")
    for day_schedule in settings.schedule:
        print(f"  {day_schedule.day.name}:")
        for slot in day_schedule.slots:
            print(f"    {slot.start_hour:02d}:{slot.start_minute:02d}"
                  f"-{slot.end_hour:02d}:{slot.end_minute:02d} "
                  f"heat={slot.heat_set}°C cool={slot.cool_set}°C")

# Update the schedule
settings = WeeklyTimerSettings(enabled=True, schedule=[
    DaySchedule(day=DayOfWeek.MONDAY, slots=[
        WeeklyTimerSlot(
            zone_id=1,
            start_hour=6, start_minute=0,
            end_hour=22, end_minute=0,
            heat_set=20,
        ),
    ]),
    DaySchedule(day=DayOfWeek.TUESDAY, slots=[
        WeeklyTimerSlot(
            zone_id=1,
            start_hour=6, start_minute=0,
            end_hour=22, end_minute=0,
            heat_set=20,
        ),
    ]),
])
await device.set_weekly_timer(settings)
```

### Consumption Data

```python
from aioaquarea import ConsumptionType
from aioaquarea.errors import DataNotAvailableError

# Get consumption for a specific day (uses cached data, refreshes if needed)
try:
    heat_kwh = await device.get_and_refresh_consumption(
        datetime.now(), ConsumptionType.HEAT
    )
    print(f"Heat consumption today: {heat_kwh} kWh")

    total_kwh = await device.get_and_refresh_consumption(
        datetime.now(), ConsumptionType.TOTAL
    )
    print(f"Total consumption today: {total_kwh} kWh")
except DataNotAvailableError:
    print("Consumption data not yet available")
```

### Demo Environment

The library supports the Panasonic Aquarea Demo Environment for testing:

```python
from aioaquarea import AquareaEnvironment

client = Client(
    session=session,
    environment=AquareaEnvironment.DEMO,
    # No username/password required for demo
)
```

### Advanced: Using Device ID Directly

If you know the device GUID (long ID), you can skip device discovery:

```python
device = await client.get_device(
    device_id="YOUR_DEVICE_GUID",
    consumption_refresh_interval=timedelta(minutes=5),
)
```

### Error Handling

```python
from aioaquarea.errors import (
    AuthenticationError,
    ApiError,
    RequestFailedError,
    DataNotAvailableError,
)

try:
    devices = await client.get_devices()
except AuthenticationError as err:
    print(f"Auth failed: {err}")
except ApiError as err:
    print(f"API error: {err}")
```

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `username` | None | Panasonic Comfort Cloud username (required for PRODUCTION) |
| `password` | None | Panasonic Comfort Cloud password (required for PRODUCTION) |
| `session` | required | aiohttp.ClientSession instance |
| `environment` | `PRODUCTION` | `AquareaEnvironment.PRODUCTION` or `AquareaEnvironment.DEMO` |
| `device_direct` | `True` | Use direct device API (production only) |
| `refresh_login` | `True` | Automatically refresh authentication when token expires |

## Supported Features

| Feature | Status |
|---------|--------|
| Device discovery | ✅ |
| Operation mode (Heat/Cool/Off/Auto) | ✅ |
| Zone temperature control | ✅ |
| Tank (DHW) control | ✅ |
| Outdoor temperature | ✅ |
| Quiet mode | ✅ |
| Force DHW / Force Heater | ✅ |
| Holiday timer | ✅ |
| Powerful time | ✅ |
| Special status (Eco/Comfort) | ✅ |
| Defrost request | ✅ |
| Consumption history | ✅ |
| Weekly timer schedule | ✅ |
| Demo environment | ✅ |
| Auto token refresh | ✅ |

## Integration with Home Assistant

This library is the foundation for the [home-assistant-aquarea](https://github.com/cjaliaga/home-assistant-aquarea) integration. Any features added here become available in Home Assistant.

## Acknowledgements

Big thanks to [ronhks](https://github.com/ronhks) for his awesome work on the [Panasonic Aquaera Smart Cloud integration with MQTT](https://github.com/ronhks/panasonic-aquarea-smart-cloud-mqtt).