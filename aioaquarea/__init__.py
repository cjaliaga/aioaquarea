"""Asynchronous library to control Panasonic Aquarea devices"""
from __future__ import annotations

from typing import Tuple

from .core import Client
from .data import (
    Device,
    DeviceAction,
    DeviceInfo,
    DeviceStatus,
    ExtendedOperationMode,
    OperationStatus,
    QuietMode,
    ForceDHW,
    Tank,
    UpdateOperationMode,
)
from .errors import (
    ApiError,
    AuthenticationError,
    AuthenticationErrorCodes,
    ClientError,
    DataNotAvailableError,
    RequestFailedError,
)
from .statistics import Consumption, ConsumptionType, DateType

__all__: Tuple[str, ...] = (
    "Client",
    "Device",
    "ClientError",
    "RequestFailedError",
    "AuthenticationError",
    "AuthenticationErrorCodes",
    "ApiError",
    "DeviceInfo",
    "DeviceStatus",
    "DeviceAction",
    "Tank",
    "OperationStatus",
    "ExtendedOperationMode",
    "UpdateOperationMode",
    "QuietMode",
    "ForceDHW",
    "DateType",
    "Consumption",
    "ConsumptionType",
    "DataNotAvailableError",
)
