#!/usr/bin/env python3
"""Lane-departure warning — entry point.

Runs as a separate Pi process: acquires camera frames, detects lane position,
and PUSHES warning events as JSON over UDP to 127.0.0.1:9100 (the shared
vehicle-state contract — see libs/protocol). It never writes files, to spare
the SD card.

Usage:
    python3 main.py                  # use config.SOURCE (camera by default)
    python3 main.py --source=file    # replay config.CLIP_PATH instead

Bench without a camera:
    python3 tools/mock_lane_writer.py    # synthetic warnings -> cluster
"""
from __future__ import annotations

import signal
import sys

import config
from pipeline import LaneDeparturePipeline


def main() -> int:
    for arg in sys.argv[1:]:
        if arg.startswith("--source="):
            config.SOURCE = arg.split("=", 1)[1]

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    LaneDeparturePipeline().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
