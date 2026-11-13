#!/usr/bin/env python3
"""Vision service — entry point (traffic signs today; lane to come).

Runs as a separate Pi process: acquires camera frames (or replays a dashcam
clip), runs the enabled stages, and PUSHES the results as JSON over UDP to the
ADAS display (the shared vehicle-state contract — see adas/protocol). It never
writes files, to spare the SD card.

Usage:
    python main.py                                   # camera (Pi)
    python main.py --source file --clip drive.mp4    # replay a dashcam clip
    python main.py --source file --clip drive.mp4 --preview   # ...and show the boxes
    python main.py --source file --clip drive.mp4 --display 192.168.1.50
        # models here (a laptop), display on the Pi at that address; run the
        # display there with --vision-host <this machine's IP>

Bench without a camera or a model:
    python tools/mock_lane_writer.py    # synthetic lane warnings
"""
from __future__ import annotations

import argparse
import signal
import sys

import config


def main() -> int:
    ap = argparse.ArgumentParser(description="ADAS vision service")
    ap.add_argument("--source", choices=["camera", "file"], default=config.SOURCE)
    ap.add_argument("--clip", default=None, help="dashcam clip for --source file")
    ap.add_argument("--weights", default=None, help="sign detector weights (b01.pt)")
    ap.add_argument("--reader", default=None, help="speed reader weights (speed_reader.pt)")
    ap.add_argument("--device", default=None, help='inference device: "cpu", "0" (CUDA), "mps"')
    ap.add_argument("--stages", default=None, help="comma list of stages, e.g. signs,lane")
    ap.add_argument("--every-frame", action="store_true",
                    help="file: process every frame instead of keeping real time")
    ap.add_argument("--loop", action="store_true", help="file: replay the clip forever")
    ap.add_argument("--preview", action="store_true", help="show frames with the detected boxes")
    ap.add_argument("--display", metavar="HOST", default=None,
                    help="send to a display on another machine (e.g. the Pi's IP), "
                         "and take its feature switches from the network")
    args = ap.parse_args()

    config.SOURCE = args.source
    if args.clip:
        config.CLIP_PATH = args.clip
    if args.weights:
        config.SIGN_WEIGHTS = args.weights
    if args.reader:
        config.SPEED_READER = args.reader
    if args.device:
        config.SIGN_DEVICE = args.device
    if args.stages is not None:
        config.STAGES = tuple(s.strip() for s in args.stages.split(",") if s.strip())
    if args.every_frame:
        config.REPLAY_REALTIME = False
    if args.loop:
        config.REPLAY_LOOP = True
    if args.display:
        config.UDP_HOST = args.display
        config.CONTROL_BIND = "0.0.0.0"

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    from runtime.scheduler import Scheduler
    Scheduler(preview=args.preview).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
