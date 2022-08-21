"""Data models for aioaquarea."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum

from .const import PANASONIC

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum


class SensorMode(StrEnum):
    DIRECT = "Direct"
    EXTERNAL = "External"


class OperationMode(StrEnum):
    COOL = "Cool"
    HEAT = "Heat"
    AUTO = "Auto"


class OperationStatus(IntEnum):
    ON = 1
    OFF = 0


class ZoneType(StrEnum):
    ROOM = "Room"


class ExtendedOperationMode(IntEnum):
    OFF = 0
    HEAT = 1
    COOL = 2
    AUTO_HEAT = 3
    AUTO_COOL = 4


class DeviceAction(IntEnum):
    """Device action"""

    OFF = 0
    IDLE = 1
    HEATING = 2
    COOLING = 3
    HEATING_WATER = 4


class DeviceDirection(IntEnum):
    """Device direction"""

    IDLE = 0
    PUMP = 1
    WATER = 2


@dataclass
class TankStatus:
    operation_status: OperationStatus
    temperature: int
    heat_max: int
    heat_min: int
    heat_set: int


@dataclass
class FaultError:
    error_message: str
    error_code: str


@dataclass
class DeviceZoneInfo:
    """Device zone info"""

    zone_id: int
    name: str
    type: ZoneType
    cool_mode: bool
    zone_sensor: SensorMode
    heat_sensor: SensorMode
    cool_sensor: SensorMode


@dataclass
class DeviceZoneStatus:
    """Device zone status"""

    zone_id: int
    temperature: int
    operation_status: OperationStatus


@dataclass
class DeviceInfo:
    """Aquarea device info"""

    device_id: str
    name: str
    long_id: str
    mode: OperationMode
    has_tank: bool
    firmware_version: str
    zones: list[DeviceZoneInfo]


@dataclass
class DeviceStatus:
    """Device status"""

    long_id: str
    operation_status: OperationStatus
    device_status: OperationStatus
    temperature_outdoor: int
    operation_mode: ExtendedOperationMode
    fault_status: list[FaultError]
    direction: int
    pump_duty: int
    tank_status: list[TankStatus]
    zones: list[DeviceZoneStatus]


class DeviceZone:
    """Device zone"""

    _info: DeviceZoneInfo
    _status: DeviceZoneStatus

    def __init__(self, info: DeviceZoneInfo, status: DeviceZoneStatus) -> None:
        self._info = info
        self._status = status

    @property
    def zone_id(self) -> int:
        return self._info.zone_id

    @property
    def name(self) -> str:
        return self._info.name

    @property
    def operation_status(self) -> OperationStatus:
        return self._status.operation_status

    @property
    def temperature(self) -> int:
        return self._status.temperature

    @property
    def cool_mode(self) -> bool:
        return self._info.cool_mode

    @property
    def type(self) -> ZoneType:
        return self._info.type


class Tank(ABC):
    """Tank"""

    _status: TankStatus

    def __init__(self, tank_status: TankStatus) -> None:
        self._status = tank_status
        super().__init__()

    @property
    def operation_status(self) -> OperationStatus:
        """The operation status of the tank"""
        return self._status.operation_status

    @property
    def temperature(self) -> int:
        """The temperature of the tank"""
        return self._status.temperature

    @property
    def heat_max(self) -> int:
        """The maximum heat temperature of the tank"""
        return self._status.heat_max

    @property
    def heat_min(self) -> int:
        """The minimum heat temperature of the tank"""
        return self._status.heat_min

    @property
    def target_temperature(self) -> int:
        """The target temperature of the tank"""
        return self._status.heat_set


class Device(ABC):
    """Aquarea Device"""

    _zones: dict[int, DeviceZone] = {}

    def __init__(self, info: DeviceInfo, status: DeviceStatus) -> None:
        self._info = info
        self._status = status
        self._tank: Tank | None = None
        self.__build_zones__()

    def __build_zones__(self) -> None:
        for zone in self._info.zones:
            zone_id = zone.zone_id
            zone_status = next(
                filter(lambda z: z.zone_id == zone_id, self._status.zones), None
            )
            self._zones[zone_id] = DeviceZone(zone, zone_status)

    @abstractmethod
    async def refresh_data(self) -> None:
        """Refresh device data"""

    @property
    def device_id(self) -> str:
        """The device id"""
        return self._info.device_id

    @property
    def long_id(self) -> str:
        """The long id of the device"""
        return self._info.long_id

    @property
    def name(self) -> str:
        """The name of the device"""
        return self._info.name

    @property
    def mode(self) -> ExtendedOperationMode:
        """The operation mode of the device"""
        return self._status.operation_mode

    @property
    def version(self) -> str:
        """The firmware version of the device"""
        return self._info.firmware_version

    @property
    def manufacturer(self) -> str:
        """The manufacturer of the device"""
        return PANASONIC

    @property
    def temperature_outdoor(self) -> int:
        """The outdoor temperature"""
        return self._status.temperature_outdoor

    @property
    def is_on_error(self) -> bool:
        """True if the device is in an error state"""
        return len(self._status.fault_status) > 0

    @property
    def operation_status(self) -> OperationStatus:
        """The operation status of the device"""
        return self._status.operation_status

    @property
    def has_tank(self) -> bool:
        """True if the device has a tank"""
        return self._info.has_tank

    @property
    def tank(self) -> Tank | None:
        """The tank of the device"""
        if self.has_tank:
            return self._tank
        return None

    @property
    def pump_duty(self) -> int:
        """The pump duty of the device"""
        return self._status.pump_duty

    @property
    def current_direction(self) -> DeviceDirection:
        """The current direction of the device"""
        return DeviceDirection(self._status.direction)

    @property
    def current_action(self) -> DeviceAction:
        """The current action the device is performing"""
        if self.operation_status == OperationStatus.OFF:
            return DeviceAction.OFF

        direction = self.current_direction
        if direction == DeviceDirection.IDLE:
            return DeviceAction.IDLE

        if (
            self.has_tank
            and direction == DeviceDirection.WATER
            and self.tank.operation_status == OperationStatus.ON
        ):
            return DeviceAction.HEATING_WATER

        mode = self.mode
        if direction == DeviceDirection.PUMP and mode != ExtendedOperationMode.OFF:

            return (
                DeviceAction.HEATING
                if mode in (ExtendedOperationMode.HEAT, ExtendedOperationMode.AUTO_HEAT)
                else DeviceAction.COOLING
            )

        return DeviceAction.IDLE

    @property
    def zones(self) -> dict[int, DeviceZone]:
        """The zones of the device"""
        return self._zones

    def support_cooling(self, zone_id: int = 1) -> bool:
        """True if the device supports cooling"""
        zone = self.zones.get(zone_id, None)
        return zone is not None and zone.cool_mode
