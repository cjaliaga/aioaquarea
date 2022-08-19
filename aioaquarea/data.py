"""Data models for aioaquarea."""
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

@dataclass
class Tank:
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
class DeviceZone:
    zone_id: int
    name: str
    type: ZoneType
    coolMode: bool
    zoneSensor: SensorMode
    heatSensor: SensorMode
    coolSensor: SensorMode

@dataclass
class DeviceZoneStatus:
    device_id: int
    temperature: int
    operation_status: OperationStatus

@dataclass
class DeviceInfo:
    device_id: str
    name: str
    long_id: str
    mode: OperationMode
    hasTank: bool
    firmware_version: str
    zones: list[DeviceZone]

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
    tank_status: list[Tank]
    zones: list[DeviceZoneStatus]

class Device(ABC):
    """Aquarea Device"""
    def __init__(self, info: DeviceInfo, status: DeviceStatus) -> None:
        self._info = info
        self._status = status

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
