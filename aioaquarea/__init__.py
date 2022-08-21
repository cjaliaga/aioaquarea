"""Asynchronous library to control Panasonic Aquarea devices"""
from __future__ import annotations

from typing import Tuple

from .core import Client, Device
from .data import DeviceAction, DeviceInfo, DeviceStatus
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
)
