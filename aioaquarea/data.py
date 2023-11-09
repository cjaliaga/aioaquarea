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


class ZoneSensor(StrEnum):
    """Zone sensor types"""

    EXTERNAL = "External"
    INTERNAL = "Internal"
    WATER_TEMPERATURE = "Water temperature"
    THERMISTOR = "Thermistor"


class SensorMode(StrEnum):
    """Sensor mode"""

    DIRECT = "Direct"
    COMPENSATION_CURVE = "Compensation curve"


class OperationMode(StrEnum):
    COOL = "Cool"
    HEAT = "Heat"
    AUTO = "Auto"


class OperationStatus(IntEnum):
    """Operation status"""

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


class UpdateOperationMode(IntEnum):
    """Values used to change the operation mode of the device"""

    OFF = 0
    HEAT = 2
    COOL = 3
    AUTO = 8


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


class QuietMode(IntEnum):
    """Quiet mode level"""

    OFF = 0
    LEVEL1 = 1
    LEVEL2 = 2
    LEVEL3 = 3


@dataclass
class TankStatus:
    """Tank status"""

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
    zone_sensor: ZoneSensor
    heat_sensor: SensorMode
    cool_sensor: SensorMode | None


@dataclass
class DeviceZoneStatus:
    """Device zone status"""

    zone_id: int
    temperature: int
    operation_status: OperationStatus
    heat_max: int | None
    heat_min: int | None
    heat_set: int | None
    cool_max: int | None
    cool_min: int | None
    cool_set: int | None


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
    quiet_mode: QuietMode


@dataclass
class OperationStatusUpdate:
    """Operation status update for a lista of devices"""

    status: list[DeviceOperationStatusUpdate]


@dataclass
class DeviceOperationStatusUpdate:
    """Device operation status update"""

    # pylint: disable=invalid-name
    deviceGuid: str
    operationStatus: OperationStatus


class DeviceZone:
    """Device zone"""

    _info: DeviceZoneInfo
    _status: DeviceZoneStatus

    def __init__(self, info: DeviceZoneInfo, status: DeviceZoneStatus) -> None:
        self._info = info
        self._status = status

    @property
    def zone_id(self) -> int:
        """Zone ID"""
        return self._info.zone_id

    @property
    def name(self) -> str:
        """Zone name"""
        return self._info.name

    @property
    def operation_status(self) -> OperationStatus:
        """Gets the zone operation status (ON/OFF)"""
        return self._status.operation_status

    @property
    def temperature(self) -> int:
        """Gets the zone temperature"""
        return self._status.temperature

    @property
    def cool_mode(self) -> bool:
        """Gets if the zone supports cool mode"""
        return self._info.cool_mode

    @property
    def type(self) -> ZoneType:
        """Gets the zone type"""
        return self._info.type

    @property
    def sensor_mode(self) -> ZoneSensor:
        """Gets the zone sensor mode"""
        return self._info.zone_sensor

    @property
    def heat_sensor_mode(self) -> SensorMode:
        """Gets the heat sensor mode"""
        return self._info.heat_sensor

    @property
    def cool_sensor_mode(self) -> SensorMode | None:
        """Gets the heat sensor mode"""
        return self._info.cool_sensor

    @property
    def cool_target_temperature(self) -> int | None:
        """Gets the target temperature for cool mode of the zone"""
        return self._status.cool_set

    @property
    def heat_target_temperature(self) -> int | None:
        """Gets the target temperature for heat mode of the zone"""
        return self._status.heat_set

    @property
    def cool_max(self) -> int | None:
        """Gets the maximum allowed temperature for cool mode of the zone"""
        return self._status.cool_max

    @property
    def cool_min(self) -> int | None:
        """Gets the minimum allowed temperature for cool mode of the zone"""
        return self._status.cool_min

    @property
    def heat_max(self) -> int | None:
        """Gets the maximum allowed temperature for heat mode of the zone"""
        return self._status.heat_max

    @property
    def heat_min(self) -> int | None:
        """Gets the minimum allowed temperature for heat mode of the zone"""
        return self._status.heat_min

    @property
    def supports_set_temperature(self) -> bool:
        """Gets if the zone supports setting the temperature"""
        return self.sensor_mode != ZoneSensor.EXTERNAL


class Tank(ABC):
    """Tank"""

    _status: TankStatus

    def __init__(self, tank_status: TankStatus, device: Device) -> None:
        self._status = tank_status
        self._device = device
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

    async def set_target_temperature(self, value: int):
        """Sets the target temperature of the tank if supported"""
        if self.target_temperature != value and self.heat_min <= value <= self.heat_max:
            await self.__set_target_temperature__(value)

    @abstractmethod
    async def __set_target_temperature__(self, value: int) -> None:
        """Sets the target temperature of the tank if supported"""

    @abstractmethod
    async def __set_operation_status__(
        self, status: OperationStatus, device_status: OperationStatus
    ) -> None:
        """Set the operation status of the device"""

    async def turn_off(self) -> None:
        """Turn off the tank"""
        if self.operation_status == OperationStatus.ON:
            # Check if device has any active zones
            device_status = (
                OperationStatus.ON
                if any(
                    zone.operation_status == OperationStatus.ON
                    for zone in self._device.zones.values()
                )
                else OperationStatus.OFF
            )
            await self.__set_operation_status__(OperationStatus.OFF, device_status)

    async def turn_on(self) -> None:
        """Turn on the tank"""
        if self.operation_status == OperationStatus.OFF:
            # Check if device has any active zones
            await self.__set_operation_status__(OperationStatus.ON, OperationStatus.ON)


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
            # pylint: disable=cell-var-from-loop
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
    def current_error(self) -> FaultError | None:
        """The current error of the device"""
        return self._status.fault_status[0] if self.is_on_error else None

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

    @property
    def quiet_mode(self) -> QuietMode:
        """The quiet mode of the device"""
        return self._status.quiet_mode

    def support_cooling(self, zone_id: int = 1) -> bool:
        """True if the device supports cooling in the given zone"""
        zone = self.zones.get(zone_id, None)
        return zone is not None and zone.cool_mode

    @abstractmethod
    async def __set_operation_status__(self, status: OperationStatus) -> None:
        """Set the operation status of the device"""

    async def turn_off(self) -> None:
        """Turn off the device"""
        if self.operation_status == OperationStatus.ON or self.is_on_error:
            await self.__set_operation_status__(OperationStatus.OFF)

    async def turn_on(self) -> None:
        """Turn on the device"""
        if self.operation_status == OperationStatus.OFF:
            await self.__set_operation_status__(OperationStatus.ON)

    @abstractmethod
    async def set_mode(
        self, mode: UpdateOperationMode, zone_id: int | None = None
    ) -> None:
        """Set the operation mode of the device. If the zone_id is provided,
         it'll try to affect only the given zone.
        Some devices don't support different modes per zone, so the specified mode (heat or cool)
         will affect the whole device.
        We will try however to turn the zone 'on' or 'off' if possible as part of the mode change.

        If we're turning the last active zone off, the device will be turned off completely,
        unless it has an active tank.

        :param mode: The mode to set
        :param zone_id: The zone id to set the mode for
        """

    @abstractmethod
    async def set_temperature(
        self, temperature: int, zone_id: int | None = None
    ) -> None:
        """Set the temperature of the zone provided for the current device mode (heat/cool).
        :param temperature: The temperature to set
        :param zone_id: The zone id to set the temperature for
        """

    @abstractmethod
    async def set_quiet_mode(
        self, mode: QuietMode
    ) -> None:
        """Set the quiet mode.
        :param mode: Quiet mode to set
        """
