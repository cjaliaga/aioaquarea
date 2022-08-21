"""Asynchronous library to control Panasonic Aquarea devices"""
from __future__ import annotations

from typing import Tuple

from .core import Client
from .data import (Device, DeviceAction, DeviceInfo, DeviceStatus,
                   ExtendedOperationMode, OperationStatus, Tank)
from .errors import (ApiError, AuthenticationError, ClientError,
                     RequestFailedError)

__all__: Tuple[str, ...] = (
    "Client",
    "Device",
    "ClientError",
    "RequestFailedError",
    "AuthenticationError",
    "ApiError",
    "DeviceInfo",
    "DeviceStatus",
    "DeviceAction",
    "Tank",
    "OperationStatus",
    "ExtendedOperationMode",
)
