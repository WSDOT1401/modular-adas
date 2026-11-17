#!/usr/bin/env python3
"""Score M1 -- the class-agnostic sign detector -- on its held-out val frames.

M1 has never been measured on the AI HAT. It says only "a sign is here", so it
cannot fail the way M2 did (whole classes annihilated); it fails by missing
signs, and the ones it misses are invisible downstream -- M2 never sees a crop
that M1 never cut.

    python  adas/vision/tools/score_m1.py --model .../m1.pt      # Mac, torch
    python3 adas/vision/tools/score_m1.py --model ~/m1_hailo_model  # Pi, chip

Recall is broken down two ways. By box size, because half the val signs are
under 48 px and that is where a detector quietly stops working. And by what the
sign actually was: M1 does not know, but M2's crops are named
<frame>_<label-line>, so every ground-truth box can be looked up by name. That
is what answers "does it miss pedestrian crossings specifically?".

A miss here is a sign the driver never hears about, so recall is the number
that matters; precision only costs M2 some wasted crops.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

VISION = Path(__file__).resolve().parents[1]
LABS = VISION.parent / "experiments/traffic-sign_recognition/thai-traffic-sign-labs/thai-traffic-sign-v3"
BUCKETS = [(0, 24), (24, 32), (32, 48), (48, 64), (64, 96), (96, 10**9)]
IOU_HIT = 0.5
MIN_N = 5


def ground_truth(data: Path):
    """[(stem, idx, xyxy, short_side_px)] from the YOLO label files."""
    from PIL import Image

    out = []
    for img in sorted((data / "images" / "val").glob("*.jpg")):
        w, h = Image.open(img).size
        lab = data / "labels" / "val" / f"{img.stem}.txt"
        for i, line in enumerate(lab.read_text().split("\n")):
            p = line.split()
            if len(p) != 5:
                continue
            cx, cy, bw, bh = (float(v) for v in p[1:])
            box = ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)
            out.append((img, i, box, min(bw * w, bh * h)))
    return out


def class_of(crops: Path) -> dict:
    """{(stem, idx): sign name}, from m2/{train,val}/<class>/<stem>_<idx>.jpg."""
    names = {}
    for split in ("train", "val"):
        for jpg in (crops / split).rglob("*.jpg"):
            stem, _, idx = jpg.stem.rpartition("_")
            if idx.isdigit():
                names[(stem, int(idx))] = jpg.parent.name
    return names


def iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(gt_boxes, pred_boxes):
    """Greedy by IoU. Returns a bool per gt box (found) and the matched-pred count."""
    found = [False] * len(gt_boxes)
    taken = set()
    pairs = sorted(((-iou(g, p), gi, pi) for gi, g in enumerate(gt_boxes)
                    for pi, p in enumerate(pred_boxes)))     # best IoU first, ties to the lower index
    for neg, gi, pi in pairs:
        score = -neg
        if score < IOU_HIT:
            break
        if not found[gi] and pi not in taken:
            found[gi], _ = True, taken.add(pi)
    return found, len(taken)


def detector(model: str, conf: float):
    """-> f(path) -> [xyxy]. A folder means the chip; a .pt means torch."""
    if Path(model).is_dir():
        sys.path.insert(0, str(VISION))
        import cv2  # type: ignore
        from signs.hailo10 import HailoSignDetector  # type: ignore

        det = HailoSignDetector(model, conf=conf)
        return lambda p: [d["box"] for d in det.detect(cv2.imread(str(p)))], det.close
    from ultralytics import YOLO  # type: ignore

    yolo = YOLO(model)
    def run(p):
        r = yolo.predict(str(p), imgsz=1280, conf=conf, verbose=False, device="mps")[0]
        return [tuple(b) for b in r.boxes.xyxy.tolist()]
    return run, lambda: None


def report(gt, found, n_pred, n_matched, names) -> None:
    if not found:
        print("\nno labelled signs in these frames")
        return
    print(f"\nrecall {np.mean(found):.1%}  ({sum(found)}/{len(found)} signs found)")
    print(f"precision {n_matched / n_pred:.1%}  ({n_pred} boxes predicted)" if n_pred else "no boxes")

    print("\nby size (short side, px):")
    for lo, hi in BUCKETS:
        sel = [f for (_, _, _, s), f in zip(gt, found) if lo <= s < hi]
        if sel:
            print(f"  {lo:>3}-{'+' if hi > 10**8 else hi:<4} {np.mean(sel):6.1%}  ({sum(sel)}/{len(sel)})")

    rows = {}
    for (img, i, _, _), f in zip(gt, found):
        rows.setdefault(names.get((img.stem, i), "?unlabelled"), []).append(f)
    print(f"\nby sign type (n >= {MIN_N}):")
    for name, fs in sorted(rows.items(), key=lambda kv: np.mean(kv[1])):
        if len(fs) >= MIN_N:
            print(f"  {name:<24} {np.mean(fs):6.1%}  ({sum(fs)}/{len(fs)})")


def selfcheck() -> None:
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((0, 0, 10, 10), (0, 0, 10, 5)) - 0.5) < 1e-9
    gt = [(0, 0, 10, 10), (50, 50, 60, 60), (100, 100, 110, 110)]
    pred = [(0, 0, 10, 10), (50, 50, 59, 59), (200, 200, 210, 210)]
    found, taken = match(gt, pred)
    assert found == [True, True, False], found       # 3rd gt missed
    assert taken == 2, taken                          # 3rd pred is a false positive
    # one pred must not satisfy two gt boxes
    found2, taken2 = match([(0, 0, 10, 10), (0, 0, 10, 10)], [(0, 0, 10, 10)])
    assert found2 == [True, False] and taken2 == 1, (found2, taken2)
    print("ok: iou and matching check out")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", help=".pt for torch, a folder for the chip")
    ap.add_argument("--data", default=str(LABS / "m1" / "floor24"))
    ap.add_argument("--crops", default=str(LABS / "m2"), help="for the per-sign-type breakdown")
    ap.add_argument("--conf", type=float, default=0.25, help="config.V3_M1_CONF, what the dash uses")
    ap.add_argument("--limit", type=int, help="first N frames only, for a smoke test")
    ap.add_argument("--dump", help="write the boxes to JSON and skip scoring (for the Pi, which "
                                   "has no labels or crops on it)")
    ap.add_argument("--preds", help="score a --dump JSON instead of running a model, so the chip "
                                    "and torch go through identical scoring code")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        selfcheck()
        return 0

    gt = ground_truth(Path(args.data))
    names = class_of(Path(args.crops)) if Path(args.crops).is_dir() else {}
    frames = sorted({img for img, _, _, _ in gt} | set((Path(args.data) / "images/val").glob("*.jpg")))
    if args.limit:                      # spread over the set: the first frames are all negatives
        frames = frames[::max(1, len(frames) // args.limit)][:args.limit]
        gt = [g for g in gt if g[0] in set(frames)]
    print(f"{args.model}\n{len(frames)} frames, {len(gt)} labelled signs, conf {args.conf}")

    if args.preds:
        loaded = json.loads(Path(args.preds).read_text())
        run, close = (lambda p: [tuple(b) for b in loaded.get(p.stem, [])]), (lambda: None)
    else:
        run, close = detector(args.model, args.conf)
    dumped = {}
    found, n_pred, n_matched = [], 0, 0
    by_frame = {}
    for img, i, box, s in gt:
        by_frame.setdefault(img, []).append(box)
    for n, img in enumerate(frames, 1):
        preds = run(img)
        if args.dump:
            dumped[img.stem] = [list(b) for b in preds]
        hits, taken = match(by_frame.get(img, []), preds)
        found.extend(hits)
        n_pred += len(preds)
        n_matched += taken
        if n % 100 == 0:
            print(f"  {n}/{len(frames)} frames", flush=True)
    close()
    if args.dump:
        Path(args.dump).write_text(json.dumps(dumped))
        print(f"\n{n_pred} boxes -> {args.dump}\nscore it on the Mac: --preds {args.dump}")
        return 0

    ordered = [g for img in frames for g in gt if g[0] == img]
    report(ordered, found, n_pred, n_matched, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
