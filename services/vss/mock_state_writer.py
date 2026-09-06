#!/usr/bin/env python3
"""
Realistic W124 driving scenario — loops forever:
  1. LAUNCH   – 0 → ~100 km/h in ~9 s  (tuned to W124 280E feel)
  2. CRUISE   – hover ~120 km/h for ~30 s with natural micro-variation
  3. BRAKE    – firm stop from ~120 in ~9 s
  4. STOPPED  – idle 3–5 s at the lights
  repeat
"""
import json
import math
import os
import pathlib
import random
import socket
import sys
import time

# Runtime dir shared with the cluster; launcher exports W124_RUNTIME_DIR, else
# fall back to the cluster's apps/cluster/ location.
_RUNTIME_DIR = pathlib.Path(
    os.environ.get("W124_RUNTIME_DIR", pathlib.Path(__file__).resolve().parents[2] / "apps" / "cluster")
)
STATE = _RUNTIME_DIR / "state.json"

# UDP mode: pass --udp [--udp-port=N] to send datagrams instead of writing a file
_UDP_PORT = 9100
for _a in sys.argv[1:]:
    if _a.startswith("--udp-port="):
        _UDP_PORT = int(_a.split("=", 1)[1])
_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if "--udp" in sys.argv else None

DT       = 0.05   # 50 ms physics ticks
JERK_MAX = 3.0    # km/h/s²  — how fast accel itself may change

# ── Throttle micro-noise ───────────────────────────────────────────────────
noise_phases = [random.uniform(0, 2 * math.pi) for _ in range(4)]
noise_freqs  = [0.7, 1.3, 2.1, 3.8]   # Hz
noise_amps   = [0.40, 0.28, 0.16, 0.09]

# ── Scenario phases ────────────────────────────────────────────────────────
# Each phase is (name, exit_condition_fn, accel_max, decel_max, target_fn)
# target_fn(speed, t_in_phase) → desired speed for this tick

def target_launch(speed, t):
    # Aim for 125 so the controller is still pushing at 100 km/h;
    # accel_max=11 gives ~9 s 0→100.
    return 125.0

def target_cruise(speed, t):
    # Slow sine drift ±6 km/h around 120, plus tiny random walk
    return 120.0 + 5.0 * math.sin(t * 0.18) + 1.5 * math.sin(t * 0.07)

def target_brake(speed, t):
    return 0.0

def target_stopped(speed, t):
    return 0.0

PHASES = [
    # name       target_fn        accel_max  decel_max  next_when
    ("LAUNCH",   target_launch,   11.0,      -4.0,      lambda s, t: s >= 118.0),
    ("CRUISE",   target_cruise,   4.5,       -6.0,      lambda s, t: t >= 30.0),
    ("BRAKE",    target_brake,     0.0,      -14.0,     lambda s, t: s < 0.8),
    ("STOPPED",  target_stopped,   0.0,       -0.0,     lambda s, t: t >= random.uniform(3.0, 5.5)),
]

phase_idx    = 0
phase_start  = time.time()
speed        = 0.0
accel        = 0.0

while True:
    t       = time.time()
    t_phase = t - phase_start

    name, target_fn, accel_max, decel_max, should_advance = PHASES[phase_idx]

    # Transition to next phase?
    if should_advance(speed, t_phase):
        phase_idx   = (phase_idx + 1) % len(PHASES)
        phase_start = t
        t_phase     = 0.0
        name, target_fn, accel_max, decel_max, should_advance = PHASES[phase_idx]

    # Proportional controller toward target
    target        = target_fn(speed, t_phase)
    error         = target - speed
    desired_accel = error * 0.35
    desired_accel = max(decel_max, min(accel_max, desired_accel))

    # Jerk-limit: accel changes smoothly
    delta = desired_accel - accel
    delta = max(-JERK_MAX * DT, min(JERK_MAX * DT, delta))
    accel += delta

    speed += accel * DT
    speed  = max(0.0, min(260.0, speed))

    # Throttle micro-noise — fades out near zero
    wobble    = 0.0
    amp_scale = min(1.0, speed / 25.0)
    for i in range(4):
        noise_phases[i] += 2 * math.pi * noise_freqs[i] * DT
        wobble           += noise_amps[i] * amp_scale * math.sin(noise_phases[i])

    v = max(0.0, min(260.0, speed + wobble))

    payload = {"speed": round(v, 1)}

    if _udp_sock:
        _udp_sock.sendto(json.dumps(payload).encode(), ("127.0.0.1", _UDP_PORT))
    else:
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        try:
            tmp.replace(STATE)
        except PermissionError:
            try:
                STATE.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            except PermissionError:
                pass
    time.sleep(DT)


DT = 0.05  # 50 ms ticks

speed        = 80.0
accel        =  0.0
mode         = "HIGHWAY"
mode_timer   = time.time() + random.uniform(15, 35)
stop_until   = 0.0
cruise_intent = 100.0

# Acceleration model
JERK_MAX = 2.0   # km/h/s²

# Throttle micro-noise phases
noise_phases = [random.uniform(0, 2 * math.pi) for _ in range(4)]
noise_freqs  = [0.7, 1.3, 2.1, 3.8]
noise_amps   = [0.35, 0.25, 0.15, 0.08]

def next_mode(current_mode, speed):
    r = random.random()
    if current_mode == "HIGHWAY":
        if r < 0.20:  return "STOPPING"      # traffic / exit
        if r < 0.45:  return "URBAN"          # town
        return "HIGHWAY"
    if current_mode == "URBAN":
        if r < 0.30:  return "STOPPING"      # red light
        if r < 0.55:  return "HIGHWAY"        # on-ramp
        return "URBAN"
    return "HIGHWAY"

def highway_intent():
    return random.uniform(70, 145)

def urban_intent():
    return random.uniform(15, 65)

while True:
    t = time.time()

    # ── Mode transitions ───────────────────────────────────────────────────
    if mode == "STOPPED" and t >= stop_until:
        mode          = "PULLING"
        cruise_intent = urban_intent() if random.random() < 0.6 else highway_intent()
        mode_timer    = t + random.uniform(8, 20)

    elif mode in ("HIGHWAY", "URBAN") and t >= mode_timer:
        new = next_mode(mode, speed)
        if new == "STOPPING":
            mode = "STOPPING"
        else:
            mode = new
            cruise_intent = highway_intent() if mode == "HIGHWAY" else urban_intent()
        mode_timer = t + random.uniform(10, 40)

    elif mode == "STOPPING" and speed < 1.0:
        mode       = "STOPPED"
        stop_until = t + random.uniform(2, 8)

    elif mode == "PULLING" and speed >= cruise_intent * 0.85:
        mode       = "URBAN" if cruise_intent < 70 else "HIGHWAY"
        mode_timer = t + random.uniform(10, 35)

    # ── Cruise intent drift (highway / urban only) ─────────────────────────
    if mode in ("HIGHWAY", "URBAN"):
        drift_rate = 0.6 if mode == "HIGHWAY" else 0.4
        cruise_intent += random.gauss(0, drift_rate * math.sqrt(DT))
        lo, hi = (70.0, 145.0) if mode == "HIGHWAY" else (15.0, 65.0)
        cruise_intent = max(lo, min(hi, cruise_intent))

    # ── Target speed for this tick ─────────────────────────────────────────
    if mode == "STOPPING":
        target, accel_max, decel_max = 0.0, 0.0, -9.0
    elif mode == "STOPPED":
        target, accel_max, decel_max = 0.0, 0.0, -9.0
    elif mode == "PULLING":
        target, accel_max, decel_max = cruise_intent, 7.0, -4.0
    elif mode == "HIGHWAY":
        target, accel_max, decel_max = cruise_intent, 4.0, -6.0
    else:  # URBAN
        target, accel_max, decel_max = cruise_intent, 3.0, -5.0

    # ── Jerk-limited acceleration ──────────────────────────────────────────
    error         = target - speed
    desired_accel = max(decel_max, min(accel_max, error * 0.3))
    delta_accel   = desired_accel - accel
    delta_accel   = max(-JERK_MAX * DT, min(JERK_MAX * DT, delta_accel))
    accel        += delta_accel

    speed        += accel * DT
    speed         = max(0.0, min(260.0, speed))

    # ── Throttle micro-noise (suppressed when stopped) ────────────────────
    wobble = 0.0
    if speed > 2.0:
        amp_scale = min(1.0, speed / 20.0)   # fade in as speed rises
        for i in range(4):
            noise_phases[i] += 2 * math.pi * noise_freqs[i] * DT
            wobble           += noise_amps[i] * amp_scale * math.sin(noise_phases[i])

    v = max(0.0, min(260.0, speed + wobble))

    payload = {"speed": round(v, 1)}

    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    try:
        tmp.replace(STATE)
    except PermissionError:
        try:
            STATE.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        except PermissionError:
            pass  # skip this tick
    time.sleep(DT)

