#!/usr/bin/env python3
"""M1 then M2, on a video, end to end -- the thing the dash actually does.

    python demo_e2e.py ../autolabel/golden-experiment/footages/golden/2026_0912_012925.MP4

M1 finds boxes and does not know what they are. M2 names each one. Anything M2
calls one of the 16 quiet classes is drawn grey and would never reach the
driver; the 13 the dash shows are drawn in colour with the name.

Run it on a clip in M1's val set. M2's val is a superset of M1's by
construction (build_m2.py, rule 1), so an M1 val clip is held out by both
models and the output is honest for the pair.

Both gates M2 was built with are applied here too, because inference has to
match training: nothing under 24px on the short side, and the crop is squared
around the box centre.
"""
import argparse
import collections
import sys
from pathlib import Path

import cv2
import torch
import torch.nn as nn
from PIL import Image
from torchvision.models import mobilenet_v3_small

import build_m2
import train_m2 as T

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402

DISPLAYED = set(classes.THAI_FINE_DISPLAYED)
QUIET_COLOR = (150, 150, 150)
SHOW_COLOR = (60, 220, 60)


def load_m2(device):
    ck = torch.load(HERE / "m2_classifier.pt", weights_only=False, map_location=device)
    m = mobilenet_v3_small()
    m.classifier[3] = nn.Linear(1024, len(ck["classes"]))
    m.load_state_dict(ck["state_dict"])
    return m.to(device).eval(), ck["classes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--m1", default=str(HERE / "m1/b02-1/best-m1-b02-1.pt"))
    ap.add_argument("--out", default=str(HERE / "demo_e2e.mp4"))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--stride", type=int, default=2, help="run every Nth frame")
    ap.add_argument("--seconds", type=float, default=0, help="0 = whole clip")
    ap.add_argument("--width", type=int, default=1280, help="output width")
    a = ap.parse_args()

    from ultralytics import YOLO
    device = ("cuda" if torch.cuda.is_available() else
              "mps" if torch.backends.mps.is_available() else "cpu")
    m1 = YOLO(a.m1)
    m2, names = load_m2(device)

    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if a.seconds:
        total = min(total, int(a.seconds * fps))
    ow = a.width
    oh = int(round(H * ow / W))
    out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), fps / a.stride, (ow, oh))
    print(f"{device}  {Path(a.video).name}  {W}x{H} {fps:.0f}fps  "
          f"{total // a.stride} frames to run -> {a.out}")

    said = collections.Counter()
    shown = quiet = small = 0
    i = 0
    while i < total:
        ok, frame = cap.read()
        if not ok:
            break
        if i % a.stride:
            i += 1
            continue
        boxes = m1.predict(frame, imgsz=1280, conf=a.conf, device=device,
                           verbose=False)[0].boxes
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        keep, crops = [], []
        for b in boxes.xyxy.cpu().tolist():
            if min(b[2] - b[0], b[3] - b[1]) < build_m2.READABLE:
                small += 1
                continue                       # M2 has never seen one this small
            keep.append(b)
            crops.append(T.NORM(build_m2.square(pil, *b)))
        said_here = []
        if crops:
            with torch.no_grad():
                p = m2(torch.stack(crops).to(device)).softmax(1)
            for b, q in zip(keep, p):
                c, j = q.max(0)
                name = names[int(j)]
                on = name in DISPLAYED
                said_here.append((b, name, float(c), on))
                shown += on
                quiet += not on
                if on:
                    said[name] += 1
        s = ow / W
        vis = cv2.resize(frame, (ow, oh))
        for b, name, c, on in said_here:
            x1, y1, x2, y2 = (int(v * s) for v in b)
            cv2.rectangle(vis, (x1, y1), (x2, y2), SHOW_COLOR if on else QUIET_COLOR,
                          2 if on else 1)
            if on:
                cv2.putText(vis, f"{name} {c:.2f}", (x1, max(14, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, SHOW_COLOR, 2, cv2.LINE_AA)
        out.write(vis)
        i += 1
        done = i // a.stride
        if done % 100 == 0:
            print(f"  {done}/{total // a.stride}", flush=True)
    cap.release(); out.release()

    print(f"\n{shown} boxes named for the dash, {quiet} kept quiet, "
          f"{small} dropped under {build_m2.READABLE}px")
    for n, k in said.most_common():
        print(f"  {k:5d}  {n}")
    print(f"\n{a.out}")


if __name__ == "__main__":
    main()
