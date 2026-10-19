#!/usr/bin/env python3
"""Run the trained detector over footage and save an annotated copy.

    python try_footage.py clip.mp4
    python try_footage.py clip.mp4 0.1     # lower conf = more boxes, more junk
    python try_footage.py some_frames/     # a folder or glob of images works too

Output lands next to this script in predict/.
"""
import pathlib
import sys

from ultralytics import YOLO

HERE = pathlib.Path(__file__).resolve().parent
WEIGHTS = HERE / "b01/weights/best.pt"

if len(sys.argv) < 2:
    sys.exit(__doc__)

YOLO(WEIGHTS).predict(
    source=sys.argv[1],
    imgsz=1280,  # trained at 1280; at the 640 default a 40 px sign disappears
    conf=float(sys.argv[2]) if len(sys.argv) > 2 else 0.25,
    save=True,
    project=HERE, name="predict", exist_ok=True,
)
print(f"wrote {HERE / 'predict'}")
