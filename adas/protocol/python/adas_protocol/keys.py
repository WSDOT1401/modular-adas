"""Canonical key names for the vehicle-state UDP contract.

These string constants are the SINGLE SOURCE OF TRUTH for the snake_case keys
carried in datagrams to udp://127.0.0.1:9100. Consumers (the ADAS display in
adas/display/, a vehicle's own cluster) **silently drop** keys they do not
know, so a typo here means data is silently lost. Import these constants
instead of hand-typing key strings.
"""

# --- Vehicle telemetry ---------------------------------------------------
SPEED = "speed"                # km/h
ODO = "odo"                    # km, total odometer
TRIP = "trip"                  # km, trip meter (wraps at 1000)
OIL_TEMP = "oil_temp"          # deg C
OUTSIDE_TEMP = "outside_temp"  # deg C
VOLTAGE = "voltage"            # volts

VEHICLE_KEYS = frozenset({SPEED, ODO, TRIP, OIL_TEMP, OUTSIDE_TEMP, VOLTAGE})

# --- ADAS / lane departure (consumed by adas/display) ---------------------
LANE_WARNING = "lane_warning"        # bool  — departure detected, should alert
LANE_DIRECTION = "lane_direction"    # "left" | "right" | "none"
LANE_CONFIDENCE = "lane_confidence"  # 0.0–1.0

LANE_DIRECTIONS = ("left", "right", "none")

# --- ADAS / forward collision (consumed by adas/display) ------------------
FCW_WARNING = "fcw_warning"          # bool  — collision risk ahead, brake
FCW_TTC = "fcw_ttc"                  # s     — time to collision (0 = unknown)

# --- ADAS / traffic signs (consumed by adas/display) ----------------------
SPEED_LIMIT = "speed_limit"          # km/h  — limit in force (0 = unknown)
SIGN_SEEN = "sign_seen"              # str   — class id of a sign just passed,
                                     #         e.g. "no_overtaking"

# --- ADAS / health (consumed by adas/display) -----------------------------
# Producers send these on every cycle; the display treats the ADAS as offline
# when no ADAS key has arrived for a few seconds.
MODULE_STATUS = "module_status"      # {"lane"|"fcw"|"signs": "on"|"paused"|"off"}
SYSTEM_FAULT = "system_fault"        # str   — "" = none, else e.g. "camera_blocked"

MODULES = ("lane", "fcw", "signs")
MODULE_STATES = ("on", "paused", "off")

ADAS_KEYS = frozenset({
    LANE_WARNING, LANE_DIRECTION, LANE_CONFIDENCE,
    FCW_WARNING, FCW_TTC, SPEED_LIMIT, SIGN_SEEN, MODULE_STATUS, SYSTEM_FAULT,
})

# --- Driver input (consumed by adas/display) ------------------------------
# One-shot events, not state: a rotary encoder, buttons or any other control
# sends one datagram per event.
INPUT = "input"                      # one of INPUT_EVENTS
INPUT_EVENTS = ("rotate_cw", "rotate_ccw", "press", "long_press")

CONTROL_KEYS = frozenset({INPUT})

ALL_KEYS = VEHICLE_KEYS | ADAS_KEYS | CONTROL_KEYS
