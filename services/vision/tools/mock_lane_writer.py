#!/usr/bin/env python3
"""Bench: emit synthetic lane-departure warnings over UDP — no camera needed.

Lets you build and test the cluster's lane-warning UI before the CV pipeline
exists. Cycles: centered -> drift left (warn) -> centered -> drift right (warn).

Analogous to services/vss/mock_state_writer.py, but for the ADAS channel.

Usage:
    python3 tools/mock_lane_writer.py [--udp-port=9100]
"""
from __future__ import annotations

import sys
import time

from w124_protocol import (
    UdpPublisher, DEFAULT_PORT, LANE_WARNING, LANE_DIRECTION, LANE_CONFIDENCE,
)

# (direction, warning_active, hold_seconds)
SCENARIO = [
    ("none",  False, 4.0),
    ("left",  True,  2.5),
    ("none",  False, 4.0),
    ("right", True,  2.5),
]


def main() -> int:
    port = DEFAULT_PORT
    for arg in sys.argv[1:]:
        if arg.startswith("--udp-port="):
            port = int(arg.split("=", 1)[1])

    pub = UdpPublisher(port=port)
    print(f"mock lane writer -> udp 127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        while True:
            for direction, active, hold in SCENARIO:
                pub.send({
                    LANE_WARNING: active,
                    LANE_DIRECTION: direction,
                    LANE_CONFIDENCE: 0.9 if active else 0.0,
                })
                print(f"  sent: warning={active} direction={direction}")
                time.sleep(hold)
    except KeyboardInterrupt:
        pass
    finally:
        pub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
