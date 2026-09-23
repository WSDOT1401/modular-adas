"""[1] Watch whole videos, follow each sign, keep the frame where it is biggest.

Fixed-interval frame sampling throws away the moment that matters: a sign is
legible for about a second as you reach it, and a screenshot every 7.5s lands
either side of it. Tracking every frame instead and keeping each track's peak
found 66 signs/clip at a median 84px, against ~16 signs at 41px for the old
sampling (measured on 2026_0912_013522.MP4).

Writes, under --out:
    frames/      peak frame per track (full image)   -> CVAT
    labels/      YOLO txt for those frames           -> CVAT
    crops/       crop_NNNN.jpg, one per track        -> gold set + step 3
    crops_ctx/   same crop with road context around it
    audit/       random frames, for spotting signs the model never proposed
    tracks.json  every detection of every track      -> step 5 propagation
    cvat_task.zip

Usage::

    python track.py --footage ../../dataset_builder/footage --out work/pass1
    python track.py --footage ... --out work/gold_src --limit 3   # gold set
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import shutil
import sys

import cv2
from ultralytics import YOLO

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import classes  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
MODEL = HERE.parent / "results/thai_runs_20260917-0529/f100/thai3-1280/weights/best.pt"

p = argparse.ArgumentParser()
p.add_argument("--footage", required=True, type=pathlib.Path)
p.add_argument("--out", required=True, type=pathlib.Path)
p.add_argument("--model", default=MODEL)
p.add_argument("--conf", type=float, default=0.15)   # low on purpose: a false box is
                                                     # one click to delete, a missed
                                                     # sign is never seen again
p.add_argument("--imgsz", type=int, default=1280)    # what the model was trained at
p.add_argument("--vid-stride", type=int, default=3)  # 10 samples/s at 30fps
p.add_argument("--min-dets", type=int, default=3)    # <3 detections is usually noise
# A track whose CLOSEST view is still tiny is one no human can name, so it gets no
# crop and never enters the fine-labelling queue. It stays in tracks.json and in
# the CVAT task, because its coarse class is still verifiable and still useful to
# the detector -- only the fine label is impossible.
p.add_argument("--min-best-side", type=float, default=60)
p.add_argument("--crop-px", type=int, default=448)   # upscale target for the VLM
p.add_argument("--ctx-scale", type=float, default=2.5)
p.add_argument("--audit-frames", type=int, default=5)
p.add_argument("--limit", type=int)                  # only N clips (for the gold set)
p.add_argument("--device", default="mps")
p.add_argument("--skip", default="", help="comma-separated clip stems to ignore")
args = p.parse_args()

skip = {s for s in args.skip.split(",") if s}
videos = sorted(v for v in args.footage.glob("*.MP4") if v.stem not in skip)
if args.limit:
    videos = videos[: args.limit]
if not videos:
    sys.exit(f"no videos in {args.footage}")

for sub in ("frames", "labels", "crops", "crops_ctx", "audit"):
    (args.out / sub).mkdir(parents=True, exist_ok=True)

model = YOLO(args.model)
all_tracks: list[dict] = []
crop_n = 0

for vid in videos:
    print(f"[{vid.stem}] tracking...", flush=True)
    # tid -> list of detections; frame_no is the SOURCE frame index
    dets: dict[int, list[dict]] = collections.defaultdict(list)
    n_read = 0
    # persist=False, not True: Model.track() registers its callbacks on the FIRST
    # call only and freezes that persist value forever (ultralytics engine/model.py).
    # One call per video means the tracker is built fresh per clip -- which is the
    # reset we want. persist=True makes clip 2 inherit clip 1's live tracks, so a
    # sign still alive at the end of one clip swallows detections from the next.
    for r in model.track(source=str(vid), stream=True, persist=False,
                         tracker="bytetrack.yaml", conf=args.conf, imgsz=args.imgsz,
                         device=args.device, verbose=False, vid_stride=args.vid_stride):
        # The loader grabs vid_stride frames and retrieves the LAST one, so the
        # first frame it yields is source index vid_stride-1, not 0. Without the
        # offset every box is recorded two frames early -- ~15px of dashcam motion
        # on a 30-60px sign, and nothing about the output looks wrong.
        frame_no = n_read * args.vid_stride + args.vid_stride - 1
        n_read += 1
        b = r.boxes
        if b is None or b.id is None:
            continue
        for i, tid in enumerate(b.id.tolist()):
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[i].tolist())
            dets[int(tid)].append({
                "frame": frame_no,
                "xyxy": [x1, y1, x2, y2],
                "cls": int(b.cls[i]),
                "conf": float(b.conf[i]),
                "size": max(x2 - x1, y2 - y1),
            })

    tracks = {t: d for t, d in dets.items() if len(d) >= args.min_dets}
    print(f"    {len(dets)} raw tracks -> {len(tracks)} kept (>={args.min_dets} dets)")

    # one decode pass: pull every frame we need from this clip
    peak = {t: max(d, key=lambda x: x["size"]) for t, d in tracks.items()}
    wanted = {pk["frame"]: [] for pk in peak.values()}
    for t, pk in peak.items():
        wanted[pk["frame"]].append(t)
    cap = cv2.VideoCapture(str(vid))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    audit = set(random.sample(range(total), min(args.audit_frames, total)))

    for fno in sorted(set(wanted) | audit):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, img = cap.read()
        if not ok:
            continue
        H, W = img.shape[:2]
        stem = f"{vid.stem}_f{fno:06d}"
        if fno in audit:
            cv2.imwrite(str(args.out / "audit" / f"{stem}.jpg"), img)
        if fno not in wanted:
            continue

        # full frame + YOLO label file for CVAT
        cv2.imwrite(str(args.out / "frames" / f"{stem}.jpg"), img)
        lines = []
        for t in wanted[fno]:
            x1, y1, x2, y2 = peak[t]["xyxy"]
            lines.append(f"{peak[t]['cls']} {((x1+x2)/2)/W:.6f} {((y1+y2)/2)/H:.6f} "
                         f"{(x2-x1)/W:.6f} {(y2-y1)/H:.6f}")
        (args.out / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")

        # crops — named neutrally so the gold set gives nothing away
        for t in wanted[fno]:
            labelable = peak[t]["size"] >= args.min_best_side
            cid = None
            if labelable:
                crop_n += 1
                cid = f"crop_{crop_n:04d}"
            x1, y1, x2, y2 = peak[t]["xyxy"]
            for name, scale in (("crops", 1.0), ("crops_ctx", args.ctx_scale)) if labelable else ():
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                hw, hh = (x2 - x1) * scale / 2, (y2 - y1) * scale / 2
                a, b_, c, d = (max(0, int(cx - hw)), max(0, int(cy - hh)),
                               min(W, int(cx + hw)), min(H, int(cy + hh)))
                patch = img[b_:d, a:c]
                if patch.size == 0:
                    continue
                if max(patch.shape[:2]) < args.crop_px:
                    s = args.crop_px / max(patch.shape[:2])
                    patch = cv2.resize(patch, None, fx=s, fy=s,
                                       interpolation=cv2.INTER_LANCZOS4)
                cv2.imwrite(str(args.out / name / f"{cid}.jpg"), patch)
            all_tracks.append({
                "crop_id": cid,
                "labelable": labelable,
                "clip": vid.stem,
                "track_id": t,
                "coarse": classes.THAI3_NAMES[peak[t]["cls"]],
                "peak": peak[t],
                "n_dets": len(tracks[t]),
                "flips_class": len({d["cls"] for d in tracks[t]}) > 1,
                "members": tracks[t],
            })
    cap.release()

(args.out / "tracks.json").write_text(json.dumps(all_tracks, indent=1))

# CVAT YOLO 1.1 import layout
task = args.out / "_cvat"
shutil.rmtree(task, ignore_errors=True)
(task / "obj_train_data").mkdir(parents=True)
for f in (args.out / "frames").glob("*.jpg"):
    shutil.copy(f, task / "obj_train_data" / f.name)
    shutil.copy(args.out / "labels" / f"{f.stem}.txt", task / "obj_train_data")
(task / "obj.names").write_text("\n".join(classes.THAI3_NAMES) + "\n")
(task / "obj.data").write_text(
    f"classes = {len(classes.THAI3_NAMES)}\ntrain = data/train.txt\n"
    "names = data/obj.names\nbackup = backup/\n")
(task / "train.txt").write_text(
    "\n".join(f"data/obj_train_data/{f.name}"
              for f in sorted((args.out / "frames").glob("*.jpg"))) + "\n")
shutil.make_archive(str(args.out / "cvat_task"), "zip", task)
shutil.rmtree(task)

flips = sum(t["flips_class"] for t in all_tracks)
lab = sum(t["labelable"] for t in all_tracks)
print(f"\n{len(all_tracks)} signs from {len(videos)} clip(s)")
print(f"  {lab} labelable (peak >= {args.min_best_side:.0f}px) -> crops written")
print(f"  {len(all_tracks)-lab} too small for anyone to name — kept for the coarse "
      "set, no crop")
print(f"  {flips} ({100*flips/max(len(all_tracks),1):.0f}%) flipped coarse class mid-track"
      " — review those first")
print(f"  crops -> {args.out/'crops'}   CVAT -> {args.out/'cvat_task.zip'}")
