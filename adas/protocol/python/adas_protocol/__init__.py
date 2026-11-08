"""adas_protocol — the shared message contract between vehicle data, ADAS
modules and the display that shows their output.

Single source of truth for the udp://127.0.0.1:9100 vehicle-state channel: the
canonical snake_case key names (``keys``) and the publisher every on-Pi
producer uses (``publisher``).
"""
from .keys import (
    SPEED, ODO, TRIP, OIL_TEMP, OUTSIDE_TEMP, VOLTAGE,
    LANE_WARNING, LANE_DIRECTION, LANE_CONFIDENCE, LANE_DIRECTIONS,
    VEHICLE_KEYS, ADAS_KEYS, ALL_KEYS,
)
from .publisher import UdpPublisher, DEFAULT_HOST, DEFAULT_PORT

__all__ = [
    "SPEED", "ODO", "TRIP", "OIL_TEMP", "OUTSIDE_TEMP", "VOLTAGE",
    "LANE_WARNING", "LANE_DIRECTION", "LANE_CONFIDENCE", "LANE_DIRECTIONS",
    "VEHICLE_KEYS", "ADAS_KEYS", "ALL_KEYS",
    "UdpPublisher", "DEFAULT_HOST", "DEFAULT_PORT",
]

__version__ = "0.1.0"
