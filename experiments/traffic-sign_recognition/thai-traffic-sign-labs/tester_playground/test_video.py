"""Play footage through the trained Thai sign model, live window. Press q/ESC to quit."""
import argparse
import time
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent / "results/thai_runs_20260917-0529/f100/thai3-1280/weights/best.pt"
VIDEO = HERE / "footage_test_youtube.mp4"

p = argparse.ArgumentParser()
p.add_argument("--model", default=MODEL)
p.add_argument("--source", default=VIDEO)
p.add_argument("--conf", type=float, default=0.35)  # tune per footage
p.add_argument("--imgsz", type=int, default=640)    # 1280 = training size, ~7 fps on mps
p.add_argument("--width", type=int, default=960)    # display width
p.add_argument("--save")                             # write annotated mp4 here (no frame drops -> preview runs slower)
p.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
args = p.parse_args()

model = YOLO(args.model)
cap = cv2.VideoCapture(str(args.source))
fps = cap.get(cv2.CAP_PROP_FPS) or 30
writer = None
t0, i = time.time(), 0

while cap.isOpened():
    # drop frames we're already late for, so playback stays in wall-clock sync
    while not args.save and i < (time.time() - t0) * fps:
        if not cap.grab():
            break
        i += 1
    ok, frame = cap.read()
    if not ok:
        break
    i += 1
    r = model.predict(frame, conf=args.conf, imgsz=args.imgsz,
                      device=args.device, verbose=False)[0]
    out = r.plot()
    h, w = out.shape[:2]
    if args.save:
        writer = writer or cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        writer.write(out)
    cv2.imshow("thai-signs", cv2.resize(out, (args.width, round(args.width * h / w))))
    if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
        break

cap.release()
if writer:
    writer.release()
cv2.destroyAllWindows()
