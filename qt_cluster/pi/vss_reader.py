#!/usr/bin/env python3
"""
W124 VSS (Vehicle Speed Sensor) reader

Reads speed pulses from the gearbox sender via a GPIO pin (conditioned
through an optocoupler circuit), calculates speed / odometer / trip,
and writes state.json at 120 ms intervals — same format as mock_state_writer.py.

Hardware required:
  See README.md → Hardware → VSS wiring circuit

Configuration:
  GPIO_PIN       — BCM pin number connected to optocoupler output
  PULSES_PER_KM  — calibrate by driving a measured km and counting pulses
                   W124 typical: 8000 (varies by gearbox/diff/tyre)

Odometer is persisted to data/odometer.json so it survives reboots.
Trip resets when state.json contains "trip_reset": true  (written by Qt app).
"""

import json
import pathlib
import threading
import time
from collections import deque

from gpiozero import Button

# ── Configuration ──────────────────────────────────────────────────────────
GPIO_PIN        = 17        # BCM GPIO pin — adjust to your wiring
PULSES_PER_KM   = 8000      # W124 typical — calibrate per vehicle
SMOOTHING       = 8         # Rolling window: number of pulses for speed avg
STALL_TIMEOUT   = 2.0       # Seconds with no pulse → speed reported as 0.0
WRITE_INTERVAL  = 0.12      # state.json write interval (seconds)
ODO_SAVE_EVERY  = 50        # Persist odometer every N write cycles (~6 s)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT       = pathlib.Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state.json"
ODO_FILE   = ROOT / "data" / "odometer.json"

# ── Derived constants ──────────────────────────────────────────────────────
METERS_PER_PULSE = 1000.0 / PULSES_PER_KM   # metres travelled per pulse

# ── Load persisted odometer ────────────────────────────────────────────────
ODO_FILE.parent.mkdir(parents=True, exist_ok=True)
try:
    _saved    = json.loads(ODO_FILE.read_text())
    total_odo = float(_saved.get("odo", 0.0))   # km
    trip_odo  = float(_saved.get("trip", 0.0))  # km
except Exception:
    total_odo = 0.0
    trip_odo  = 0.0

# ── Shared pulse state ─────────────────────────────────────────────────────
pulse_times = deque(maxlen=SMOOTHING + 1)   # monotonic timestamps of recent pulses
lock        = threading.Lock()
last_pulse  = time.monotonic()


# ── Pulse callback (runs in gpiozero GPIO thread) ─────────────────────────
def on_pulse() -> None:
    global last_pulse, total_odo, trip_odo
    now = time.monotonic()
    with lock:
        pulse_times.append(now)
        last_pulse = now
        total_odo += METERS_PER_PULSE / 1000.0   # accumulate km
        trip_odo  += METERS_PER_PULSE / 1000.0


# ── Speed calculation ──────────────────────────────────────────────────────
def calc_speed() -> float:
    """Return current speed in km/h using rolling pulse window."""
    with lock:
        pts        = list(pulse_times)
        last_seen  = last_pulse

    # No pulses received yet, or vehicle has stalled
    if len(pts) < 2 or (time.monotonic() - last_seen) > STALL_TIMEOUT:
        return 0.0

    elapsed = pts[-1] - pts[0]
    if elapsed <= 0:
        return 0.0

    pulse_count  = len(pts) - 1
    freq         = pulse_count / elapsed          # pulses/sec
    speed_kmh    = (freq / PULSES_PER_KM) * 3600.0
    return round(speed_kmh, 1)


# ── Persist odometer ───────────────────────────────────────────────────────
def save_odo() -> None:
    with lock:
        data = {"odo": round(total_odo, 3), "trip": round(trip_odo, 3)}
    ODO_FILE.write_text(json.dumps(data))


# ── GPIO setup ─────────────────────────────────────────────────────────────
# pull_up=True  → idle HIGH, pulse pulls LOW (matches optocoupler output)
# bounce_time   → 0.5 ms debounce; safe up to ~250 km/h at 8000 pulses/km
sensor = Button(GPIO_PIN, pull_up=True, bounce_time=0.0005)
sensor.when_pressed = on_pulse

print(f"VSS reader started — GPIO BCM{GPIO_PIN}, {PULSES_PER_KM} pulses/km")
print(f"State file : {STATE_FILE}")
print(f"Odometer   : {ODO_FILE}  (odo={total_odo:.1f} km, trip={trip_odo:.3f} km)")

# ── Main write loop ────────────────────────────────────────────────────────
save_counter = 0

while True:
    speed = calc_speed()

    with lock:
        odo  = round(total_odo, 1)
        trip = round(trip_odo, 3)

    STATE_FILE.write_text(json.dumps({
        "speed": speed,
        "odo":   odo,
        "trip":  trip,
    }))

    save_counter += 1
    if save_counter >= ODO_SAVE_EVERY:
        save_odo()
        save_counter = 0

    time.sleep(WRITE_INTERVAL)
