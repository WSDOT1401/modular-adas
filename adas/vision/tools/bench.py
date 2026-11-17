#!/usr/bin/env python3
"""Bench run: the whole system live on a dashcam clip, as if the camera were
on the car.

Starts three processes and wires them over UDP, the same way they run on the
Pi:

    vision service ── clip at real-time pace ─► b01 + speed reader ──┐
    speed_sim ── simulated speed sensor ──────────────────────────────┼─► display (:9100)
    display ── feature on/off (menu) ─► vision (:9102) ◄──────────────┘

The clip plays at its own pace: when inference can't keep up, frames are
dropped (as a live camera would), so what you see is what the Pi would
manage at this machine's speed. A preview window shows the frame with the
boxes; the display shows what the driver gets. Quit with q/Esc in the
preview, or Ctrl+C here: all three stop.

    python tools/bench.py --clip D:/clips/drive.mp4 --display path/to/adas_display
    python tools/bench.py --clip drive.mp4 --display none     # display already running (Pi service)
    python tools/bench.py --clip drive.mp4 --speed fixed:45   # hold 45 km/h
    python tools/bench.py --clip drive.mp4 --speed none --loop --shape rect
    python tools/bench.py --clip drive.mp4 --pi 192.168.1.50      # models here, display on the Pi

With --pi, the models and the speed run on this machine (a laptop with the
horsepower) and everything goes over the network to the display on the Pi,
which must be started with --vision-host <this machine's IP> so it listens
on the network and sends the menu's feature switches back here.

The speed is simulated (the clip's own speed isn't known), so OVERSPEED trips
whenever the simulated car is over a limit the clip just showed.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

VISION = Path(__file__).resolve().parents[1]
DISPLAY_TOOLS = VISION.parent / "display" / "tools"


def default_display() -> str:
    exe = "adas_display.exe" if os.name == "nt" else "adas_display"
    return str(VISION.parent / "display" / "build" / exe)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run vision + speed + display on a dashcam clip")
    ap.add_argument("--clip", required=True, help="dashcam clip to play as the camera")
    ap.add_argument("--display", default=default_display(),
                    help='display executable, or "none" if one is already running')
    ap.add_argument("--shape", choices=("round", "rect"), default="round")
    ap.add_argument("--speed", default="city",
                    help='"city" (town and highway), "cycle", "fixed:KMH" or "none"')
    ap.add_argument("--device", help='inference device: "cpu", "0" (CUDA), "mps"')
    ap.add_argument("--no-preview", action="store_true", help="no window with the boxes")
    ap.add_argument("--loop", action="store_true", help="replay the clip forever")
    ap.add_argument("--pi", metavar="IP", help="the display runs on the Pi at this address")
    args = ap.parse_args()

    if not Path(args.clip).is_file():
        ap.error(f"clip not found: {args.clip}")
    py = sys.executable
    procs = []
    if args.pi:
        args.display = "none"

    def start(name, cmd, **kw):
        print(f"[bench] {name}: {' '.join(cmd)}", flush=True)
        procs.append((name, subprocess.Popen(cmd, **kw)))

    try:
        if args.display != "none":
            if not Path(args.display).is_file():
                ap.error(f"display not found: {args.display} (build it, pass --display PATH, "
                         'or --display none if it is already running)')
            start("display", [args.display, "--windowed", "--shape", args.shape])
            time.sleep(1.5)   # let it bind :9100 before data arrives

        if args.speed != "none":
            mode = []
            if args.speed == "cycle":
                mode = ["--cycle"]
            elif args.speed.startswith("fixed:"):
                mode = ["--fixed", args.speed.split(":", 1)[1]]
            elif args.speed != "city":
                ap.error(f"unknown --speed {args.speed!r}")
            env = dict(os.environ, ADAS_UDP_TARGETS=f"{args.pi}:9100") if args.pi else None
            start("speed", [py, str(DISPLAY_TOOLS / "speed_sim.py"), *mode], env=env)

        cmd = [py, "main.py", "--source", "file", "--clip", args.clip]
        if args.device:
            cmd += ["--device", args.device]
        if not args.no_preview:
            cmd.append("--preview")
        if args.loop:
            cmd.append("--loop")
        if args.pi:
            cmd += ["--display", args.pi]
        start("vision", cmd, cwd=str(VISION))
        vision = procs[-1][1]

        # Run until the vision service ends (clip over, or q in the preview)
        # or anything else dies.
        while vision.poll() is None:
            for name, p in procs:
                if p.poll() is not None and p is not vision:
                    print(f"[bench] {name} exited ({p.returncode}); stopping", flush=True)
                    return 1
            time.sleep(0.3)
        return vision.returncode or 0
    except KeyboardInterrupt:
        return 0
    finally:
        for name, p in reversed(procs):
            if p.poll() is None:
                p.terminate()
        for name, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
