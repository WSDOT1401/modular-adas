"""adas_protocol — the shared message contract between vehicle data, ADAS
modules, driver controls and the displays that show their output.

Single source of truth for the udp://127.0.0.1:9100 channel: the canonical
snake_case key names (``keys``) and the publisher every on-Pi producer uses
(``publisher``).
"""
from .keys import (
    SPEED, ODO, TRIP, OIL_TEMP, OUTSIDE_TEMP, VOLTAGE,
    LANE_WARNING, LANE_DIRECTION, LANE_CONFIDENCE, LANE_DIRECTIONS,
    FCW_WARNING, FCW_TTC, LEAD_VEHICLE, SPEED_LIMIT, SIGN_SEEN, MODULE_STATUS, SYSTEM_FAULT,
    MODULES, MODULE_STATES, INPUT, INPUT_EVENTS, FEATURE_ENABLE,
    VEHICLE_KEYS, ADAS_KEYS, CONTROL_KEYS, ALL_KEYS,
)
from .publisher import (
    UdpPublisher, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_CONTROL_PORT, TARGETS_ENV,
    parse_targets,
)

__all__ = [
    "SPEED", "ODO", "TRIP", "OIL_TEMP", "OUTSIDE_TEMP", "VOLTAGE",
    "LANE_WARNING", "LANE_DIRECTION", "LANE_CONFIDENCE", "LANE_DIRECTIONS",
    "FCW_WARNING", "FCW_TTC", "LEAD_VEHICLE", "SPEED_LIMIT", "SIGN_SEEN", "MODULE_STATUS",
    "SYSTEM_FAULT", "MODULES", "MODULE_STATES", "INPUT", "INPUT_EVENTS",
    "FEATURE_ENABLE", "DEFAULT_CONTROL_PORT",
    "VEHICLE_KEYS", "ADAS_KEYS", "CONTROL_KEYS", "ALL_KEYS",
    "UdpPublisher", "DEFAULT_HOST", "DEFAULT_PORT", "TARGETS_ENV",
    "parse_targets",
]

__version__ = "0.2.0"
