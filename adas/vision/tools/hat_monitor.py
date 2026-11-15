#!/usr/bin/env python3
"""Live view of the AI HAT while the vision service runs: load, fps,
latency and chip temperature. btop can't see the HAT, and on the Hailo-10H
HailoRT 5.1.1's ``hailortcli monitor`` shows nothing.

The vision service (signs/hailo10.py) writes the numbers to
/dev/shm/adas-hat.json once a second; this only reads them, so it can run
in any terminal on the Pi, or over ssh:

    python3 tools/hat_monitor.py          # refreshes until Ctrl+C
    python3 tools/hat_monitor.py --once   # one reading, for scripts

Load is the chip's frame rate against the most it does with the same
number of frames in flight (51 fps for b01 at 3). It's not a reading from
inside the chip: HailoRT 5.1.1 doesn't give one on the Hailo-10H.

Plain Python, no packages: it doesn't need the venv.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

STATS_FILE = Path("/dev/shm/adas-hat.json")    # same as signs/hailo10.py
STALE_S = 3.0
BAR = 30


def read() -> "dict | None":
    try:
        stats = json.loads(STATS_FILE.read_text())
    except (OSError, ValueError):
        return None
    return stats if time.time() - stats.get("time", 0) < STALE_S else None


def bar(fraction: float) -> str:
    full = round(max(0.0, min(fraction, 1.0)) * BAR)
    return "█" * full + "░" * (BAR - full)


def render(s: "dict | None") -> str:
    if s is None:
        return ("AI HAT+ 2 (Hailo-10H)\n\n"
                "  no readings: the vision service isn't running on the HAT\n"
                "  (start it, e.g. python main.py --source camera)\n")
    load = s.get("load")
    lines = [
        f"AI HAT+ 2 (Hailo-10H)   {s.get('model', '?')}   pid {s.get('pid', '?')}",
        "",
        (f"  Load     {bar(load)} {load * 100:5.1f} %" if load is not None else "  Load     ?"),
        f"  Rate     {s.get('fps', 0):5.1f} fps   (most: {s.get('max_fps') or '?'} fps with "
        f"{s.get('depth', '?')} frames in flight)",
    ]
    if s.get("latency_ms") is not None:
        lines.append(f"  Latency  {s['latency_ms']:5.1f} ms per frame on the chip   "
                     f"in flight {s.get('in_flight', '?')}/{s.get('depth', '?')}")
    if s.get("temp_c") is not None:
        lines.append(f"  Chip     {s['temp_c']:5.1f} °C")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Live AI HAT load, fps, latency, temperature")
    ap.add_argument("--once", action="store_true", help="print one reading and exit")
    args = ap.parse_args()
    if args.once:
        sys.stdout.write(render(read()))
        return 0
    try:
        while True:
            sys.stdout.write("\033[H\033[J" + render(read()) + "\n  Ctrl+C to quit\n")
            sys.stdout.flush()
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
