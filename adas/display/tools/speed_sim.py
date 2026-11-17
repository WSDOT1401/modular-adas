#!/usr/bin/env python3
"""Simulated speed input for the bench: a car driving around town and on the
highway, sent as {"speed": km/h} over UDP like a real speed sensor would.

Run it beside the vision service replaying a dashcam clip, and the display
gets both halves of the picture: signs and limits from the clip, speed from
here, so OVERSPEED trips whenever the simulated car is over a limit the clip
just showed. (The clip's real speed isn't known, so the two don't match.)

Ported from the W124 repo's vss/mock_state_writer.py (its city/highway model),
with speeds that fit Thai roads: town 20–60 km/h, highway 80–125 km/h.

    python tools/speed_sim.py                  # city and highway, forever
    python tools/speed_sim.py --cycle          # launch, cruise, brake, stop, repeat
    python tools/speed_sim.py --fixed 72       # hold one speed
    python tools/speed_sim.py --port 9101      # one display on another port

Sends to 127.0.0.1:9100 by default, or to every target in ADAS_UDP_TARGETS.
"""
from __future__ import annotations

import argparse
import math
import random
import time

from adas_protocol import SPEED, UdpPublisher

DT = 0.05            # 50 ms ticks: 20 datagrams a second
JERK_MAX = 2.0       # km/h/s², how fast acceleration itself may change

TOWN = (20.0, 60.0)
HIGHWAY = (80.0, 125.0)


class Throttle:
    """A driver's foot is never perfectly still: a few small sine wobbles."""

    def __init__(self) -> None:
        self.phases = [random.uniform(0, 2 * math.pi) for _ in range(4)]
        self.freqs = [0.7, 1.3, 2.1, 3.8]
        self.amps = [0.35, 0.25, 0.15, 0.08]

    def wobble(self, speed: float) -> float:
        if speed <= 2.0:
            return 0.0
        scale = min(1.0, speed / 20.0)
        total = 0.0
        for i in range(4):
            self.phases[i] += 2 * math.pi * self.freqs[i] * DT
            total += self.amps[i] * scale * math.sin(self.phases[i])
        return total


class CityHighway:
    """Town and highway stretches, stops at lights, pulling away again."""

    def __init__(self) -> None:
        self.mode = "PULLING"
        self.intent = random.uniform(*TOWN)
        self.until = time.monotonic() + random.uniform(10, 25)
        self.stop_until = 0.0

    def target(self, speed: float, now: float):
        """-> (target km/h, max accel, max decel) for this tick."""
        if self.mode == "STOPPED" and now >= self.stop_until:
            self._set("PULLING", now)
            self.intent = random.uniform(*TOWN) if random.random() < 0.6 else random.uniform(*HIGHWAY)
        elif self.mode in ("HIGHWAY", "TOWN") and now >= self.until:
            r = random.random()
            if r < 0.25:
                self._set("STOPPING", now)
            else:
                self._set("HIGHWAY" if r < 0.6 else "TOWN", now)
                self.intent = random.uniform(*(HIGHWAY if self.mode == "HIGHWAY" else TOWN))
        elif self.mode == "STOPPING" and speed < 1.0:
            self._set("STOPPED", now)
            self.stop_until = now + random.uniform(2, 8)
        elif self.mode == "PULLING" and speed >= self.intent * 0.85:
            self._set("TOWN" if self.intent < 70 else "HIGHWAY", now)

        if self.mode in ("HIGHWAY", "TOWN"):             # the driver's intent drifts
            lo, hi = HIGHWAY if self.mode == "HIGHWAY" else TOWN
            self.intent = max(lo, min(hi, self.intent + random.gauss(0, 0.6 * math.sqrt(DT))))

        if self.mode in ("STOPPING", "STOPPED"):
            return 0.0, 0.0, -9.0
        if self.mode == "PULLING":
            return self.intent, 7.0, -4.0
        if self.mode == "HIGHWAY":
            return self.intent, 4.0, -6.0
        return self.intent, 3.0, -5.0

    def _set(self, mode: str, now: float) -> None:
        if mode != self.mode:
            print(f"{mode.lower():9s}" + (f" aiming for {self.intent:.0f} km/h" if mode in ("HIGHWAY", "TOWN", "PULLING") else ""),
                  flush=True)
        self.mode = mode
        self.until = now + random.uniform(10, 40)


class Cycle:
    """Launch to ~100 in ~9 s, cruise ~90 for 30 s, brake hard, wait, repeat."""

    PHASES = [
        # name      target                                    accel  decel  done when
        ("launch",  lambda t: 105.0,                          11.0,  -4.0,  lambda s, t: s >= 95.0),
        ("cruise",  lambda t: 90 + 5 * math.sin(t * 0.18),     4.5,  -6.0,  lambda s, t: t >= 30.0),
        ("brake",   lambda t: 0.0,                             0.0, -14.0,  lambda s, t: s < 0.8),
        ("stopped", lambda t: 0.0,                             0.0,   0.0,  lambda s, t: t >= 4.0),
    ]

    def __init__(self) -> None:
        self.index = 0
        self.start = time.monotonic()
        print(self.PHASES[0][0], flush=True)

    def target(self, speed: float, now: float):
        name, target, accel, decel, done = self.PHASES[self.index]
        if done(speed, now - self.start):
            self.index = (self.index + 1) % len(self.PHASES)
            self.start = now
            name, target, accel, decel, done = self.PHASES[self.index]
            print(name, flush=True)
        return target(now - self.start), accel, decel


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulated speed for the ADAS display")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--cycle", action="store_true", help="launch, cruise, brake, stop, repeat")
    mode.add_argument("--fixed", type=float, metavar="KMH", help="hold one speed")
    ap.add_argument("--port", type=int, help="send to 127.0.0.1:PORT only")
    args = ap.parse_args()

    pub = UdpPublisher(port=args.port) if args.port else UdpPublisher()
    print(f"speed -> {pub.targets}", flush=True)
    model = None if args.fixed is not None else (Cycle() if args.cycle else CityHighway())
    throttle = Throttle()
    speed = accel = 0.0
    try:
        while True:
            now = time.monotonic()
            if model is None:
                shown = args.fixed
            else:
                target, accel_max, decel_max = model.target(speed, now)
                desired = max(decel_max, min(accel_max, (target - speed) * 0.3))
                accel += max(-JERK_MAX * DT, min(JERK_MAX * DT, desired - accel))
                speed = max(0.0, min(200.0, speed + accel * DT))
                shown = max(0.0, speed + throttle.wobble(speed))
            pub.send({SPEED: round(shown, 1)})
            time.sleep(DT)
    except KeyboardInterrupt:
        pass
    finally:
        pub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
