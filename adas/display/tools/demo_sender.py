#!/usr/bin/env python3
"""Drive the ADAS display from the bench, no camera or car needed.

Sends the same scenarios as the display's built-in demo (qml/Scenarios.js),
over the real UDP path, so it also tests the wiring between processes.

    python3 adas/display/tools/demo_sender.py                 # cycle all, 4 s each
    python3 adas/display/tools/demo_sender.py --scenario fcw  # hold one
    python3 adas/display/tools/demo_sender.py --input long_press   # one control event

Targets: --port, else ADAS_UDP_TARGETS, else 127.0.0.1:9100.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import time

from adas_protocol import (
    FCW_TTC, FCW_WARNING, INPUT, INPUT_EVENTS, LANE_DIRECTION, LANE_WARNING,
    MODULE_STATUS, SIGN_SEEN, SPEED, SPEED_LIMIT, SYSTEM_FAULT, UdpPublisher,
)

BASE = {
    SPEED: 82,
    SPEED_LIMIT: 90,
    LANE_WARNING: False,
    LANE_DIRECTION: "none",
    FCW_WARNING: False,
    FCW_TTC: 0,
    SYSTEM_FAULT: "",
    MODULE_STATUS: {"lane": "on", "fcw": "on", "signs": "on"},
}

CHANGES = {
    "cruise": {},
    "lane_left": {SPEED: 84, LANE_WARNING: True, LANE_DIRECTION: "left"},
    "lane_right": {SPEED: 84, LANE_WARNING: True, LANE_DIRECTION: "right"},
    "fcw": {SPEED: 76, FCW_WARNING: True, FCW_TTC: 1.2},
    "overspeed": {SPEED: 103},
    "new_sign": {SPEED: 58, SPEED_LIMIT: 60, SIGN_SEEN: "speed_limit_60"},
    "fault": {
        SPEED: 80,
        SYSTEM_FAULT: "camera_blocked",
        MODULE_STATUS: {"lane": "paused", "fcw": "paused", "signs": "paused"},
    },
}


def payload(name: str) -> dict:
    p = copy.deepcopy(BASE)
    p.update(copy.deepcopy(CHANGES[name]))
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", choices=sorted(CHANGES), help="hold one scenario")
    ap.add_argument("--seconds", type=float, default=4.0, help="per scenario when cycling")
    ap.add_argument("--rate", type=float, default=5.0, help="datagrams per second")
    ap.add_argument("--input", choices=INPUT_EVENTS, help="send one control event and exit")
    ap.add_argument("--port", type=int, help="send to 127.0.0.1:PORT only")
    args = ap.parse_args()

    pub = UdpPublisher(port=args.port) if args.port else UdpPublisher()
    with pub:
        if args.input:
            pub.send({INPUT: args.input})
            return 0

        names = [args.scenario] if args.scenario else list(CHANGES)
        print(f"sending to {pub.targets} — Ctrl+C to stop")
        period = 1.0 / args.rate
        try:
            for name in itertools.cycle(names):
                if not args.scenario:
                    print(f"  {name}")
                end = time.monotonic() + (args.seconds if not args.scenario else float("inf"))
                while time.monotonic() < end:
                    pub.send(payload(name))
                    time.sleep(period)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
