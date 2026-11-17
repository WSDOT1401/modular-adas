"""Traffic-sign classes: which detector outputs the driver is told about.

The class list itself is baked into the detector weights (``r.names`` in
ultralytics), so there is no id -> name table to keep in sync. The names are
the Thai fine classes from
``adas/experiments/traffic-sign_recognition/classes.py`` (stop,
pedestrian_crossing, speed_limit, ...); the display has a word for each.
"""
from __future__ import annotations

# The one class whose number is read separately (by the speed reader). It is
# published as sign_seen "speed_limit", with the value in speed_limit.
SPEED_LIMIT = "speed_limit"

# Catch-alls: "clearly a sign, just not one we know". Telling the driver
# "other regulatory sign" is noise, so these are never published.
IGNORED = frozenset({"other_regulatory", "other_warning", "information"})


def publishable(name: str) -> bool:
    """True if a detection of this class should reach the display."""
    return bool(name) and name not in IGNORED
