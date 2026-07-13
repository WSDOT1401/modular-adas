"""Canonical key names for the W124 vehicle-state UDP contract.

These string constants are the SINGLE SOURCE OF TRUTH for the snake_case keys
carried in datagrams to udp://127.0.0.1:9100. The C++ consumer
(``VehicleState::applyJson``) recognizes the VEHICLE_* keys below; unknown keys
are **silently dropped**, so a typo here means data is silently lost. Import
these constants instead of hand-typing key strings.
"""

# --- Vehicle telemetry (recognized by VehicleState::applyJson today) -------
SPEED = "speed"                # km/h
ODO = "odo"                    # km, total odometer
TRIP = "trip"                  # km, trip meter (wraps at 1000)
OIL_TEMP = "oil_temp"          # deg C
OUTSIDE_TEMP = "outside_temp"  # deg C
VOLTAGE = "voltage"            # volts

VEHICLE_KEYS = frozenset({SPEED, ODO, TRIP, OIL_TEMP, OUTSIDE_TEMP, VOLTAGE})

# --- ADAS / lane departure (PROPOSED — not yet parsed by the C++ consumer) -
# Sending these on the wire is harmless (ignored) until VehicleState gains the
# matching Q_PROPERTYs + applyJson parsing. They are defined here so producers
# and the eventual consumer share one spelling. See libs/protocol/README.md.
LANE_WARNING = "lane_warning"        # bool  — departure detected, should alert
LANE_DIRECTION = "lane_direction"    # "left" | "right" | "none"
LANE_CONFIDENCE = "lane_confidence"  # 0.0–1.0

LANE_DIRECTIONS = ("left", "right", "none")
ADAS_KEYS = frozenset({LANE_WARNING, LANE_DIRECTION, LANE_CONFIDENCE})

ALL_KEYS = VEHICLE_KEYS | ADAS_KEYS
