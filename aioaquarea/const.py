"""Constants definition"""

from enum import IntEnum


AQUAREA_SERVICE_BASE = "https://aquarea-smart.panasonic.com/"
AQUAREA_SERVICE_DEMO_BASE = "https://demo.aquarea-smart.panasonic.com/"
AQUAREA_SERVICE_LOGIN = "remote/v1/api/auth/login"
AQUAREA_SERVICE_DEVICES = "remote/v1/api/devices"
AQUAREA_SERVICE_CONSUMPTION = "remote/v1/api/consumption"
AQUAREA_SERVICE_CONTRACT = "remote/contract"
AQUAREA_SERVICE_A2W_STATUS_DISPLAY = "remote/a2wStatusDisplay"

PANASONIC = "Panasonic"


class AquareaEnvironment(IntEnum):
    """Aquarea environment"""

    PRODUCTION = 0
    DEMO = 1
