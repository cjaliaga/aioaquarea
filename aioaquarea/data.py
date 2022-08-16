from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum

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
    def __init__(self, info: DeviceInfo, status: DeviceStatus) -> None:
        self._info = info
        self._status = status
    
    @abstractmethod
    async def refresh_data(self) -> None:
        pass

    @property
    def temperature_outdoor(self) -> int:
        return self._status.temperature_outdoor
        