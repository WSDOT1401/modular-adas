#!/usr/bin/env python3
"""M1 finds the signs, M2 names them -- on the Pi, from a clip or a camera.

    python run.py ../test-clip.mp4
    python run.py ../test-clip.mp4 --out annotated.mp4
    python run.py 0 --stride 1
    python run.py --selfcheck

Self-contained on purpose. ``central/`` is what gets copied to the Pi, so this
file carries its own copy of the two geometry rules M2 was trained with rather
than importing them from the lab tree:

* nothing under 24 source px on the short side is shown to M2
* the crop is SQUARED around the box centre before it is resized

That is the entire contract between training and inference, and breaking it
fails silently -- the model still answers, just worse. ``--selfcheck`` asserts
both against the originals in the lab tree, which exists in this repo and does
not exist on the Pi.

The class list, the 13 classes the dash shows, and the crop size all travel
inside ``m2.pt``, so there is no mapping file here to drift out of sync.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import time

import cv2
import torch
import torch.nn as nn
from PIL import Image
from torchvision.models import mobilenet_v3_small
from torchvision.transforms import v2

HERE = pathlib.Path(__file__).resolve().parent

READABLE = 24   # source px, short side -- the smallest crop M2 was ever trained on
# ImageNet stats, because M2 starts from ImageNet weights. A mismatch here costs
# several points and looks exactly like a bad model.
NORM = v2.Compose([v2.ToImage(), v2.ToDtype(torch.float32, scale=True),
                   v2.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])


def square(im, x1, y1, x2, y2, size):
    """Box -> square crop around its centre, clamped to the frame.

    Square because the synthetic training crops are composited onto a square
    canvas. Training on squares and testing on stretched rectangles is a free
    way to lose points.
    """
    half = min(max(x2 - x1, y2 - y1) / 2, im.width / 2, im.height / 2)
    cx = min(max((x1 + x2) / 2, half), im.width - half)
    cy = min(max((y1 + y2) / 2, half), im.height - half)
    return im.crop((round(cx - half), round(cy - half),
                    round(cx + half), round(cy + half))).resize(
                        (size, size), Image.LANCZOS)


def load_m2(path, device):
    ck = torch.load(path, weights_only=False, map_location=device)
    m = mobilenet_v3_small()
    m.classifier[3] = nn.Linear(1024, len(ck["classes"]))
    m.load_state_dict(ck["state_dict"])
    return m.to(device).eval(), ck["classes"], set(ck["displayed"]), ck["size"]


def selfcheck():
    """The inlined geometry still matches the lab tree it was copied from."""
    import sys
    lab = HERE / "../../traffic-sign_recognition/thai-traffic-sign-labs/thai-traffic-sign-v3"
    if not lab.exists():
        print("lab tree not here (this is the Pi) -- geometry unchecked")
        return
    sys.path.insert(0, str(lab.resolve()))
    import build_m2
    assert READABLE == build_m2.READABLE, (READABLE, build_m2.READABLE)
    # Noise, not a blank canvas: two different crops of flat grey are identical
    # bytes, so a flat image would pass this check with the geometry wrong.
    im = Image.frombytes("RGB", (640, 480),
                         bytes((i * 7919) % 256 for i in range(640 * 480 * 3)))
    for box in [(10, 10, 50, 90), (0, 0, 5, 5), (600, 450, 700, 500), (100, 100, 101, 101)]:
        assert square(im, *box, build_m2.SIZE).tobytes() == \
               build_m2.square(im, *box).tobytes(), box
    _m, names, shown, size = load_m2(HERE / "m2.pt", "cpu")
    assert size == build_m2.SIZE and len(names) == 29 and len(shown) == 13
    print(f"ok  {len(names)} classes, {len(shown)} shown, {size}px, floor {READABLE}px")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", help="video path, or a camera index")
    ap.add_argument("--m1", default=str(HERE / "m1.pt"))
    ap.add_argument("--m2", default=str(HERE / "m2.pt"))
    ap.add_argument("--imgsz", type=int, default=1280,
                    help="M1 was trained here; at 640 the small signs stop existing")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--stride", type=int, default=2, help="run every Nth frame")
    ap.add_argument("--seconds", type=float, default=0, help="0 = the whole clip")
    ap.add_argument("--out", help="write an annotated mp4 (slow on a Pi)")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    if not a.source:
        ap.error("need a video path or a camera index (or --selfcheck)")

    from ultralytics import YOLO
    dev = ("cuda" if torch.cuda.is_available() else
           "mps" if torch.backends.mps.is_available() else "cpu")
    m1 = YOLO(a.m1)
    m2, names, shown, size = load_m2(a.m2, dev)

    cap = cv2.VideoCapture(int(a.source) if a.source.isdigit() else a.source)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {a.source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W, H = int(cap.get(3)), int(cap.get(4))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 10**9
    if a.seconds:
        total = min(total, int(a.seconds * fps))
    writer = None
    if a.out:
        writer = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"),
                                 fps / a.stride, (W, H))
    print(f"{dev}  {W}x{H} {fps:.0f}fps  M1@{a.imgsz}  "
          f"{total // a.stride} frames{'  -> ' + a.out if a.out else ''}")

    said = collections.Counter()
    t1 = t2 = 0.0
    ran = boxes_seen = small = 0
    i = 0
    while i < total:
        ok, frame = cap.read()
        if not ok:
            break
        if i % a.stride:
            i += 1
            continue
        ran += 1
        t = time.perf_counter()
        det = m1.predict(frame, imgsz=a.imgsz, conf=a.conf, device=dev,
                         verbose=False)[0].boxes.xyxy.cpu().tolist()
        t1 += time.perf_counter() - t

        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        keep, crops = [], []
        for b in det:
            boxes_seen += 1
            if min(b[2] - b[0], b[3] - b[1]) < READABLE:
                small += 1
                continue                      # M2 has never seen one this small
            keep.append(b)
            crops.append(NORM(square(pil, *b, size)))
        hits = []
        if crops:
            t = time.perf_counter()
            with torch.no_grad():
                p = m2(torch.stack(crops).to(dev)).softmax(1)
            t2 += time.perf_counter() - t
            for b, q in zip(keep, p):
                c, j = q.max(0)
                name = names[int(j)]
                hits.append((b, name, float(c), name in shown))
                if name in shown:
                    said[name] += 1
        if writer is not None:
            for b, name, c, on in hits:
                x1, y1, x2, y2 = (int(v) for v in b)
                col = (60, 220, 60) if on else (150, 150, 150)
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2 if on else 1)
                if on:
                    cv2.putText(frame, f"{name} {c:.2f}", (x1, max(14, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
            writer.write(frame)
        i += 1
        if ran % 50 == 0:
            print(f"\r  {ran}/{total // a.stride}  "
                  f"M1 {1000*t1/ran:.0f}ms  M2 {1000*t2/max(1,ran):.0f}ms",
                  end="", flush=True)
    cap.release()
    if writer is not None:
        writer.release()

    print(f"\n\n{ran} frames, {boxes_seen} boxes ({small} under {READABLE}px, dropped)")
    print(f"  M1 {1000*t1/max(1,ran):6.1f} ms/frame")
    print(f"  M2 {1000*t2/max(1,ran):6.1f} ms/frame")
    print(f"  end to end {ran/max(1e-9, t1+t2):.1f} fps on the frames it ran")
    print(f"\nwhat the dash would have said ({sum(said.values())} times):")
    for k, n in said.most_common():
        print(f"  {n:5d}  {k}")


if __name__ == "__main__":
    main()
