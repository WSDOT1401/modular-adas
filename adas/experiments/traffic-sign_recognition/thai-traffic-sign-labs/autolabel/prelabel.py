#!/usr/bin/env python3
"""Move one batch of picked frames from "a human chose these" to "YOLO can train on these".

    prelabel.py new        b01 --picks picks.csv --workspace app/workspace/frames
    prelabel.py detect     b01
    prelabel.py to-colab   b01
    prelabel.py from-colab b01 ~/Downloads/predictions.csv
    prelabel.py to-cvat    b01
    prelabel.py from-cvat  b01 ~/Downloads/task_export.zip
    prelabel.py build
    prelabel.py status

**A batch is a folder, and everything about a batch lives in that folder.** That
is the whole fix for the old ``work/pass1-2-3`` layout, where you could not tell
whether ``predictions_new.csv`` belonged to pass 2 or pass 3.

**The stage a batch has reached is never written down.** ``status`` works it out
from which files exist, the same way the web app derives its clip icons. A state
you never store cannot drift out of sync with what actually happened.

Two rules survive from the golden experiment, both learned the expensive way:

* A frame is a picture, not a row. Every sign visible in a training image must
  carry a box, or the image teaches the detector that a sign is background. So
  ``to-cvat`` draws *every* box on a frame, and ``build`` drops a whole frame if
  any sign on it came back unnamed.
* An empty frame is real training data, but only once a human has confirmed it is
  empty. They go to CVAT like everything else.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import json
import pathlib
import random
import shutil
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402

BATCHES = HERE / "batches"
DATASET = HERE / "dataset"
MODEL = HERE.parent / "results/thai_runs_20260917-0529/f100/thai3-1280/weights/best.pt"

# A reviewer needs a word for every verdict, including "there is a sign here but
# I cannot name it". Deleting the box says something different -- it says "not a
# sign at all" -- and the two must not be confused, because an unnamed sign
# poisons its whole frame while a deleted box does not.
SPECIAL = ("too_small", "dont_know", "composite", "not_a_sign")
NAMES = list(classes.THAI_FINE_NAMES) + list(SPECIAL)
IDX = {n: i for i, n in enumerate(NAMES)}

CROP_PX = 448        # upscale target for the VLM; matches the golden experiment
VAL_FRAC = 0.20


# ----------------------------------------------------------------- plumbing --

def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def catch_all(parent: str) -> str:
    group = classes.THAI_FINE_BY_PARENT[parent]
    return next((o for o in group if o.startswith("other_")), group[-1])


def rows(path: pathlib.Path) -> list[dict]:
    return list(csv.DictReader(path.open())) if path.exists() else []


def write_rows(path: pathlib.Path, header, body) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(body)


def find(bid: str) -> pathlib.Path:
    """A batch id may be given short (``b01``) or in full (``b01-2026-10-13``)."""
    if (BATCHES / bid).is_dir():
        return BATCHES / bid
    hits = sorted(p for p in BATCHES.glob(f"{bid}-*") if p.is_dir())
    if not hits:
        sys.exit(f"no batch {bid!r} under {BATCHES}. `prelabel.py status` lists them.")
    if len(hits) > 1:
        sys.exit(f"{bid!r} matches {len(hits)} batches: {[p.name for p in hits]}")
    return hits[0]


def need(d: pathlib.Path, name: str, fix: str) -> pathlib.Path:
    """Refuse clearly, and say which command produces the missing thing."""
    p = d / name
    if not p.exists():
        sys.exit(f"{d.name} has no {name}\n  run: prelabel.py {fix} {d.name.split('-')[0]}")
    return p


def stage_of(d: pathlib.Path) -> str:
    """Derived, never stored -- see the module docstring."""
    if (d / "reviewed.csv").exists():
        return "reviewed -> build"
    if (d / "review.zip").exists():
        return "in review on CVAT"
    if (d / "predictions.csv").exists():
        return "named -> to-cvat"
    if (d / "crops.zip").exists():
        return "waiting on colab"
    if (d / "boxes.csv").exists():
        return "detected -> to-colab"
    if (d / "manifest.csv").exists():
        return "picked -> detect"
    return "empty"


# ---------------------------------------------------------------------- new --

def create(bid: str, picks, workspace: pathlib.Path) -> pathlib.Path:
    """Copy the picked frames into a new batch folder.

    ``picks`` is an iterable of ``(clip, frame_id, picked_as)``. The web app calls
    this directly so that there is exactly one implementation of what a batch is.
    """
    from PIL import Image

    day = datetime.date.today().isoformat()
    d = BATCHES / f"{bid}-{day}"
    if d.exists():
        sys.exit(f"{d} already exists — delete it or pick another id")
    (d / "frames").mkdir(parents=True)

    body, clips, missing = [], set(), []
    boxes, detected = [], []
    scores: dict[str, dict] = {}
    for clip, frame_id, picked_as in picks:
        src = workspace / clip / "full" / f"{frame_id}.jpg"
        if not src.exists():
            missing.append(frame_id)
            continue
        shutil.copy(src, d / "frames" / f"{frame_id}.jpg")
        w, h = Image.open(src).size
        body.append((frame_id, clip, int(frame_id.rsplit("_f", 1)[-1]), picked_as, w, h))
        clips.add(clip)

        # Carry the boxes the web app already found. The detector runs once per
        # frame for the whole pipeline -- once for the contact-sheet badge and
        # never again -- so `detect` has only crops left to cut.
        if clip not in scores:
            f = workspace / clip / "scores.json"
            scores[clip] = json.loads(f.read_text()).get("frames", {}) if f.exists() else {}
        if frame_id in scores[clip]:
            detected.append(frame_id)
            for b in scores[clip][frame_id]:
                boxes.append((frame_id, *b["xyxy"], b["coarse"], b["conf"]))

    write_rows(d / "manifest.csv",
               ["frame_id", "clip", "frame_no", "picked_as", "width", "height"],
               sorted(body))
    if boxes:
        write_rows(d / "boxes.csv",
                   ["frame_id", "x1", "y1", "x2", "y2", "coarse", "conf"], sorted(boxes))
    (d / "batch.json").write_text(json.dumps({
        "id": bid, "created": day, "clips": sorted(clips),
        "n_frames": len(body), "detector": str(MODEL),
        "detected": sorted(detected),
    }, indent=2) + "\n")

    empty = sum(1 for r in body if r[3] == "empty")
    if detected:
        print(f"  {len(boxes)} boxes carried over from the web app's scoring "
              f"({len(body)-len(detected)} frames still need detect)")
    print(f"{d}: {len(body)} frames from {len(clips)} clips")
    print(f"  {len(body)-empty} with a sign / {empty} empty "
          f"({100*empty/len(body):.0f}% empty)" if body else "  (no frames)")
    if missing:
        print(f"  !! {len(missing)} frames not in the cache, skipped: {missing[:3]}")
    return d


def cmd_new(a):
    picks = [(r["clip"], r["frame_id"], r.get("picked_as", "sign"))
             for r in rows(a.picks)]
    if not picks:
        sys.exit(f"{a.picks} has no rows")
    create(a.bid, picks, a.workspace)


# ------------------------------------------------------------------- detect --

def cmd_detect(a):
    import cv2

    d = find(a.bid)
    man = rows(need(d, "manifest.csv", "new"))
    meta = json.loads((d / "batch.json").read_text())
    # Which frames the model has SEEN, not which produced boxes. A frame with no
    # sign on it writes no row to boxes.csv, so the two are not the same thing --
    # and inferring one from the other would re-run the detector on every empty
    # frame, forever, which is exactly the frames you have most of.
    have = set(meta.get("detected", []))
    todo = [r for r in man if r["frame_id"] not in have]

    body = [(r["frame_id"], r["x1"], r["y1"], r["x2"], r["y2"], r["coarse"], r["conf"])
            for r in rows(d / "boxes.csv")]
    if todo:
        from ultralytics import YOLO
        model = YOLO(a.model)
        paths = [str(d / "frames" / f"{r['frame_id']}.jpg") for r in todo]
        for r, res in zip(todo, model.predict(source=paths, imgsz=a.imgsz,
                                              conf=a.conf, stream=True, verbose=False)):
            for b in res.boxes:
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                body.append((r["frame_id"], round(x1, 1), round(y1, 1), round(x2, 1),
                             round(y2, 1), classes.THAI3_NAMES[int(b.cls)],
                             round(float(b.conf), 3)))
    write_rows(d / "boxes.csv",
               ["frame_id", "x1", "y1", "x2", "y2", "coarse", "conf"], sorted(body))
    meta["detected"] = sorted(have | {r["frame_id"] for r in todo})
    (d / "batch.json").write_text(json.dumps(meta, indent=2) + "\n")

    # crops: one per box, upscaled so a 40px sign is not shown to the VLM as 40px.
    crops = d / "crops"
    shutil.rmtree(crops, ignore_errors=True)
    crops.mkdir()
    smap, per_frame = [], collections.defaultdict(int)
    for fid, x1, y1, x2, y2, coarse, _conf in sorted(body):
        i = per_frame[fid]
        per_frame[fid] += 1
        cid = f"{fid}_b{i}"
        img = cv2.imread(str(d / "frames" / f"{fid}.jpg"))
        if img is None:
            continue
        H, W = img.shape[:2]
        a_, b_ = max(0, int(float(x1))), max(0, int(float(y1)))
        c_, e_ = min(W, int(float(x2))), min(H, int(float(y2)))
        patch = img[b_:e_, a_:c_]
        if patch.size == 0:
            continue
        if max(patch.shape[:2]) < CROP_PX:
            s = CROP_PX / max(patch.shape[:2])
            patch = cv2.resize(patch, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
        cv2.imwrite(str(crops / f"{cid}.jpg"), patch)
        smap.append((cid, fid, x1, y1, x2, y2, coarse))

    write_rows(d / "source_map.csv",
               ["crop_id", "frame_id", "x1", "y1", "x2", "y2", "coarse"], smap)
    empty = sum(1 for r in man if r["frame_id"] not in {s[1] for s in smap})
    print(f"{d.name}: {len(body)} boxes on {len(man)} frames "
          f"({len(todo)} frames newly detected, {len(man)-len(todo)} already had boxes)")
    print(f"  {len(smap)} crops -> {crops}")
    print(f"  {empty} frames have no box at all (background for training)")
    print(f"\nNext: prelabel.py to-colab {a.bid}")


# ------------------------------------------------------------------- colab --

def cmd_to_colab(a):
    d = find(a.bid)
    need(d, "crops", "detect")
    out = d / "crops.zip"
    stage = d / "_pack"
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "crops").mkdir(parents=True)
    for p in (d / "crops").glob("*.jpg"):
        shutil.copy(p, stage / "crops" / p.name)
    shutil.copy(d / "source_map.csv", stage / "source_map.csv")
    # classes.py rides along: on Colab there is no repo to import it from.
    shutil.copy(HERE.parents[1] / "classes.py", stage / "classes.py")
    shutil.copy(HERE / "qwen_label.py", stage / "qwen_label.py")
    if out.exists():
        out.unlink()
    shutil.make_archive(str(out.with_suffix("")), "zip", stage)
    shutil.rmtree(stage)
    n = len(list((d / "crops").glob("*.jpg")))
    print(f"{out}: {n} crops ({out.stat().st_size/1e6:.1f} MB)")
    print(f"\nUpload it to Drive, run the notebook, download predictions.csv, then:"
          f"\n  prelabel.py from-colab {a.bid} ~/Downloads/predictions.csv")


def cmd_from_colab(a):
    d = find(a.bid)
    mine = {r["crop_id"] for r in rows(need(d, "source_map.csv", "detect"))}
    got = rows(a.csv)
    if not got:
        sys.exit(f"{a.csv} is empty")
    col = next((c for c in ("pred", "label") if c in got[0]), None)
    if col is None:
        sys.exit(f"{a.csv}: expected a 'pred' or 'label' column, got {list(got[0])}")
    # Belongs-to-this-batch check: a predictions.csv from another batch would
    # relabel everything with plausible-looking nonsense and never complain.
    theirs = {r["crop_id"] for r in got}
    overlap = mine & theirs
    if not overlap:
        sys.exit(f"{a.csv} has no crop in {d.name} — wrong batch?\n"
                 f"  its first id: {next(iter(theirs))}\n  expected like: {next(iter(mine))}")
    write_rows(d / "predictions.csv", ["crop_id", "pred"],
               sorted((r["crop_id"], r[col]) for r in got if r["crop_id"] in mine))
    unknown = sum(1 for r in got if r[col] not in IDX)
    print(f"{d/'predictions.csv'}: {len(overlap)}/{len(mine)} crops named")
    if len(theirs - mine):
        print(f"  {len(theirs-mine)} rows were for other batches — ignored")
    if unknown:
        print(f"  {unknown} labels are not class names; they fall back to the "
              f"coarse catch-all in the CVAT task")
    print(f"\nNext: prelabel.py to-cvat {a.bid}")


# -------------------------------------------------------------------- cvat --

def cmd_to_cvat(a):
    d = find(a.bid)
    man = rows(need(d, "manifest.csv", "new"))
    smap = rows(need(d, "source_map.csv", "detect"))
    pred = {r["crop_id"]: r["pred"] for r in rows(d / "predictions.csv")}
    size = {r["frame_id"]: (int(r["width"]), int(r["height"])) for r in man}

    by_frame = collections.defaultdict(list)
    n_pred = 0
    for r in smap:
        lab = pred.get(r["crop_id"], "")
        if lab in IDX:
            n_pred += 1
        else:
            lab = catch_all(r["coarse"])
        by_frame[r["frame_id"]].append(
            (lab, tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2"))))

    stage = d / "_review"
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "obj_train_data").mkdir(parents=True)
    listed = []
    for r in man:
        fid = r["frame_id"]
        src = d / "frames" / f"{fid}.jpg"
        if not src.exists():
            continue
        shutil.copy(src, stage / "obj_train_data" / src.name)
        W, H = size[fid]
        # An empty frame still gets a .txt -- an empty one. A frame with no label
        # file at all is ambiguous: nobody can tell "confirmed empty" from "not
        # exported".
        (stage / "obj_train_data" / f"{fid}.txt").write_text("".join(
            f"{IDX[l]} {((x1+x2)/2)/W:.6f} {((y1+y2)/2)/H:.6f} "
            f"{(x2-x1)/W:.6f} {(y2-y1)/H:.6f}\n"
            for l, (x1, y1, x2, y2) in by_frame.get(fid, [])))
        listed.append(fid)

    (stage / "obj.names").write_text("\n".join(NAMES) + "\n")
    (stage / "obj.data").write_text(
        f"classes = {len(NAMES)}\ntrain = data/train.txt\n"
        "names = data/obj.names\nbackup = backup/\n")
    (stage / "train.txt").write_text(
        "\n".join(f"data/obj_train_data/{s}.jpg" for s in listed) + "\n")
    out = d / "review.zip"
    if out.exists():
        out.unlink()
    shutil.make_archive(str(out.with_suffix("")), "zip", stage)
    shutil.rmtree(stage)

    n_box = sum(len(v) for v in by_frame.values())
    n_empty = len(listed) - len(by_frame)
    print(f"{out}: {len(listed)} frames, {n_box} boxes ({out.stat().st_size/1e6:.1f} MB)")
    print(f"  {n_pred} boxes pre-named by Qwen, {n_box-n_pred} fell back to a catch-all")
    print(f"  {n_empty} frames are empty — the reviewer confirms that, which is "
          f"where a missed sign gets caught")
    print(f"\nIn CVAT: create a task with these {len(NAMES)} labels in obj.names order,\n"
          f"upload the zip as the data, then Actions -> Upload annotations -> "
          f"'YOLO 1.1' -> the same zip.\nWhen your group is done: Export task dataset "
          f"-> 'YOLO 1.1' (untick Save images), then\n  prelabel.py from-cvat {a.bid} "
          f"~/Downloads/<export>.zip")


def cmd_from_cvat(a):
    d = find(a.bid)
    man = rows(need(d, "manifest.csv", "new"))
    size = {r["frame_id"]: (int(r["width"]), int(r["height"])) for r in man}
    proposed = collections.defaultdict(list)
    pred = {r["crop_id"]: r["pred"] for r in rows(d / "predictions.csv")}
    for r in rows(d / "source_map.csv"):
        lab = pred.get(r["crop_id"], "")
        proposed[r["frame_id"]].append(
            (lab if lab in IDX else catch_all(r["coarse"]),
             tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2"))))

    out, seen = [], set()
    kept = relabelled = added = 0
    with zipfile.ZipFile(a.zip) as z:
        members = {pathlib.PurePath(n).name: n for n in z.namelist()}
        if "obj.names" not in members:
            sys.exit(f"{a.zip} has no obj.names — is this a 'YOLO 1.1' export?")
        # Trust the export's own order. CVAT lets anyone reorder the label list,
        # and an off-by-one here relabels every box in the batch silently.
        names = z.read(members["obj.names"]).decode().split()
        unknown = [n for n in names if n not in IDX]
        if unknown:
            print(f"  !! labels not in our class list, kept verbatim: {unknown}")

        for r in man:
            fid = r["frame_id"]
            txt = members.get(f"{fid}.txt")
            if txt is None:
                continue
            seen.add(fid)
            W, H = size[fid]
            mine = proposed.get(fid, [])
            used = set()
            for line in z.read(txt).decode().splitlines():
                if not line.strip():
                    continue
                c, cx, cy, w, h = (float(v) for v in line.split())
                x1, y1 = (cx - w / 2) * W, (cy - h / 2) * H
                x2, y2 = (cx + w / 2) * W, (cy + h / 2) * H
                lab = names[int(c)]
                out.append((fid, round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1), lab))
                # Match back to what we proposed, for the accept rate only. The
                # reviewed box is authoritative either way.
                best, score = None, 0.0
                for i, (_l, b) in enumerate(mine):
                    s = iou((x1, y1, x2, y2), b)
                    if i not in used and s > score:
                        best, score = i, s
                if best is not None and score >= a.iou:
                    used.add(best)
                    kept += mine[best][0] == lab
                    relabelled += mine[best][0] != lab
                else:
                    added += 1
            proposed[fid] = [b for i, b in enumerate(mine) if i in used]

    missing = [r["frame_id"] for r in man if r["frame_id"] not in seen]
    write_rows(d / "reviewed.csv",
               ["frame_id", "x1", "y1", "x2", "y2", "label"], sorted(out))

    n_prop = sum(1 for r in rows(d / "source_map.csv"))
    deleted = n_prop - kept - relabelled
    print(f"{d/'reviewed.csv'}: {len(out)} boxes on {len(seen)} reviewed frames")
    print(f"\nWhat the review cost, against {n_prop} boxes we proposed:")
    print(f"  {kept:5d} accepted as-is      ({100*kept/n_prop:.0f}%)" if n_prop else "")
    print(f"  {relabelled:5d} kept, relabelled")
    print(f"  {deleted:5d} deleted (not a sign)")
    print(f"  {added:5d} drawn by hand (signs the detector missed)")
    if missing:
        print(f"\n  !! {len(missing)} frames are not in the export — NOT reviewed, "
              f"and they will be left out of the dataset.")
    print(f"\nNext: prelabel.py build")


# ------------------------------------------------------------------- build --

def cmd_build(a):
    """Every reviewed batch -> one YOLO dataset.

    Split is by **clip**, not by frame. Frames 2 s apart can hold the same
    physical sign, so a frame-level split would put one view of a sign in train
    and another in val and quietly inflate the score.
    """
    fine = {n: i for i, n in enumerate(classes.THAI_FINE_NAMES)}
    want = sorted(p for p in BATCHES.glob("*") if (p / "reviewed.csv").exists())
    if a.only:
        want = [find(b) for b in a.only]
    if not want:
        sys.exit(f"no reviewed batch under {BATCHES} — finish one with from-cvat first")

    frames, dropped, size = {}, collections.Counter(), {}
    for d in want:
        clip_of = {r["frame_id"]: r["clip"] for r in rows(d / "manifest.csv")}
        by_frame = collections.defaultdict(list)
        for r in rows(d / "reviewed.csv"):
            by_frame[r["frame_id"]].append(r)
        for fid, clip in clip_of.items():
            box = by_frame.get(fid, [])
            labs = [b["label"] for b in box]
            # not_a_sign is a deleted box: drop the box, keep the frame.
            box = [b for b in box if b["label"] != "not_a_sign"]
            # ...but an unnamed *sign* poisons its whole frame. Leaving it
            # unboxed would teach the detector that this sign is background.
            bad = [l for l in labs if l in SPECIAL and l != "not_a_sign"]
            if bad:
                dropped[bad[0]] += 1
                continue
            if any(b["label"] not in fine for b in box):
                dropped["unknown_label"] += 1
                continue
            frames[fid] = (d, clip, box)
        size.update(((d, r["frame_id"]), (int(r["width"]), int(r["height"])))
                    for r in rows(d / "manifest.csv"))

    clips = sorted({c for _d, c, _b in frames.values()})
    random.Random(a.seed).shuffle(clips)
    n_val = max(1, round(len(clips) * VAL_FRAC)) if len(clips) > 1 else 0
    val = set(clips[:n_val])

    shutil.rmtree(DATASET, ignore_errors=True)
    for split in ("train", "val"):
        (DATASET / "images" / split).mkdir(parents=True)
        (DATASET / "labels" / split).mkdir(parents=True)

    count = collections.Counter()
    per_split = collections.Counter()
    for fid, (d, clip, box) in sorted(frames.items()):
        split = "val" if clip in val else "train"
        per_split[split] += 1
        src = d / "frames" / f"{fid}.jpg"
        W, H = size[(d, fid)]
        shutil.copy(src, DATASET / "images" / split / f"{fid}.jpg")
        lines = []
        for b in box:
            x1, y1, x2, y2 = (float(b[k]) for k in ("x1", "y1", "x2", "y2"))
            count[b["label"]] += 1
            lines.append(f"{fine[b['label']]} {((x1+x2)/2)/W:.6f} {((y1+y2)/2)/H:.6f} "
                         f"{(x2-x1)/W:.6f} {(y2-y1)/H:.6f}")
        (DATASET / "labels" / split / f"{fid}.txt").write_text(
            ("\n".join(lines) + "\n") if lines else "")

    (DATASET / "data.yaml").write_text(
        f"path: {DATASET}\ntrain: images/train\nval: images/val\n"
        f"nc: {len(classes.THAI_FINE_NAMES)}\n"
        f"names: {list(classes.THAI_FINE_NAMES)}\n")

    empty = sum(1 for _f, (_d, _c, b) in frames.items() if not b)
    print(f"{DATASET}: {len(frames)} frames, {sum(count.values())} boxes "
          f"from {len(want)} batch(es)")
    print(f"  {per_split['train']} train / {per_split['val']} val "
          f"(split by clip: {len(clips)-n_val} train clips, {n_val} val)")
    print(f"  {empty} frames are background (no boxes)")
    if dropped:
        print(f"  dropped {sum(dropped.values())} frames holding a sign nobody "
              f"could name: {dict(dropped)}")
    print("\n  class                     boxes")
    for n, c in count.most_common():
        print(f"  {n:26s} {c:4d}")
    thin = [n for n in classes.THAI_FINE_NAMES if count[n] == 0]
    if thin:
        print(f"\n  {len(thin)} classes have no boxes yet: {', '.join(thin)}")


# ------------------------------------------------------------------ status --

def cmd_status(_a):
    got = sorted(p for p in BATCHES.glob("*") if p.is_dir())
    if not got:
        print(f"no batches yet under {BATCHES}")
        return
    for d in got:
        meta = json.loads((d / "batch.json").read_text()) if (d / "batch.json").exists() else {}
        n = meta.get("n_frames", "?")
        print(f"  {d.name:22s} {str(n):>4s} frames   {stage_of(d)}")


def selfcheck(_a=None):
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    # A reviewer nudging a box must still count as the same box, or the accept
    # rate reads as "deleted + added" and the labour saving looks like zero.
    assert iou((0, 0, 100, 100), (3, 3, 103, 103)) > 0.85
    assert iou((0, 0, 100, 100), (10, 10, 90, 90)) > 0.6
    assert iou((0, 0, 100, 100), (90, 0, 190, 100)) < 0.5
    assert catch_all("Information") == "information"
    assert catch_all("Warning") == "other_warning"
    assert NAMES[:len(classes.THAI_FINE_NAMES)] == list(classes.THAI_FINE_NAMES), \
        "fine classes must keep their index order or every exported box shifts class"
    assert "not_a_sign" in SPECIAL
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="picked frames -> a new batch folder")
    p.add_argument("bid")
    p.add_argument("--picks", type=pathlib.Path, required=True,
                   help="csv: clip, frame_id, picked_as")
    p.add_argument("--workspace", type=pathlib.Path,
                   default=HERE / "app/workspace/frames")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("detect", help="boxes for every frame, and one crop per box")
    p.add_argument("bid")
    p.add_argument("--model", type=pathlib.Path, default=MODEL)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--conf", type=float, default=0.25)
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("to-colab", help="-> crops.zip, for Drive")
    p.add_argument("bid")
    p.set_defaults(fn=cmd_to_colab)

    p = sub.add_parser("from-colab", help="Qwen's predictions.csv back in")
    p.add_argument("bid")
    p.add_argument("csv", type=pathlib.Path)
    p.set_defaults(fn=cmd_from_colab)

    p = sub.add_parser("to-cvat", help="-> review.zip, for your group")
    p.add_argument("bid")
    p.set_defaults(fn=cmd_to_cvat)

    p = sub.add_parser("from-cvat", help="the reviewed CVAT export back in")
    p.add_argument("bid")
    p.add_argument("zip", type=pathlib.Path)
    p.add_argument("--iou", type=float, default=0.5,
                   help="how close a reviewed box must be to count as the one we proposed")
    p.set_defaults(fn=cmd_from_cvat)

    p = sub.add_parser("build", help="every reviewed batch -> one YOLO dataset")
    p.add_argument("--only", nargs="*", help="these batch ids instead of all reviewed")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_build)

    sub.add_parser("status", help="where every batch is").set_defaults(fn=cmd_status)
    sub.add_parser("selfcheck").set_defaults(fn=selfcheck)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
