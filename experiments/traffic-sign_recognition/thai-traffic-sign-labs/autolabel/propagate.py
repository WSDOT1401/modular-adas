#!/usr/bin/env python3
"""[5] Confirmed labels -> a YOLO dataset covering every frame each sign appeared in.

One human decision per sign becomes a label on every frame the tracker followed
that sign through -- including the frames where it is a 20px smudge nobody could
have labelled by hand. That multiplier is the only reason tracking was worth it.

    python propagate.py --report                 # numbers only, writes nothing
    python propagate.py --out work/dataset       # extract frames + YOLO labels
    python propagate.py --selfcheck

Three rules here are not negotiable, because each one silently inflates a score
if you get it wrong:

* **Split by track, never by frame.** Two frames 0.1 s apart are near-identical
  pictures of one sign. Put one in train and the other in val and the val number
  measures memorisation, not recognition.
* **Every sign on a kept frame gets a box.** A frame is one training image. A
  real sign left unlabelled on it actively teaches the detector that signs are
  background. Frames that hold a sign nobody could name (``too_small``,
  ``composite``) are dropped for exactly that reason.
* **``not_a_sign`` boxes stay unlabelled on purpose.** Those are the detector's
  own false positives -- shop banners, taillights. Leaving them in the image
  with no box is how the detector learns to stop firing on them.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import classes  # noqa: E402

# Dispositions meaning "a real sign we could not put a fine label on". Their
# frames are unusable as training images -- see rule 2 above. ``not_a_sign`` is
# deliberately NOT here.
BLOCK = ("too_small", "composite", "dont_know")


def catch_all(parent: str) -> str:
    """The class that means 'a real sign of this type, none of the above'."""
    group = classes.THAI_FINE_BY_PARENT[parent]
    return next((o for o in group if o.startswith("other_")), group[-1])


def sample(members, step):
    """Keep a detection once the box has changed size by >= `step` since the last
    one kept.

    A sign tracked for 3 seconds gives ~30 detections. At a steady distance those
    are 30 copies of one picture and they teach the model nothing it did not
    learn from the first. The variation worth keeping is scale: the same sign at
    17 px, 40 px and 98 px is three genuinely different training examples.
    """
    kept, last = [], 0.0
    for d in sorted(members, key=lambda m: m["frame"]):
        if not kept or abs(d["size"] - last) / max(last, 1e-9) >= step:
            kept.append(d)
            last = d["size"]
    return kept


def fold(labels, min_signs):
    """Map each fine class to itself, or to its parent's catch-all if it is thin.

    A class backed by one distinct sign cannot be learned (the model memorises
    that one signpost) and cannot be evaluated (one sign splits into train or
    val, never both). Left in, it adds a 0.0 AP row to the results table and
    overstates how many classes the dataset really covers. Folded, it at least
    makes the catch-all class honest about what it contains.
    """
    signs = collections.Counter(labels.values())
    return {name: (catch_all(classes.THAI_FINE_PARENT[name])
                   if n < min_signs and name != catch_all(classes.THAI_FINE_PARENT[name])
                   else name)
            for name, n in signs.items()}


def plan(root, step, val_frac, min_signs, seed):
    """Decide everything before touching a video file. Pure, so --report is free."""
    tracks = json.loads((root / "tracks.json").read_text())
    key = {r["crop_id"]: r["label"]
           for r in csv.DictReader((root / "answer_key.csv").open())}

    fine = set(classes.THAI_FINE_NAMES)
    labelled = {c: l for c, l in key.items() if l in fine}

    # Dispositions are filtered out of answer_key.csv, so the folders are the
    # only record of which crops were "a real sign, unnameable". Union over all
    # annotators: after `gold.py apply` they agree, and before it the cautious
    # read is the right one.
    blocked = {c for c, l in key.items() if l in BLOCK}
    for d in BLOCK:
        blocked |= {f.stem for f in root.glob(f"labels/*/{d}/*.jpg")}

    by_id = {t["crop_id"]: t for t in tracks if t.get("crop_id")}
    bad = set()
    for cid in blocked:
        if cid in by_id:
            bad |= {(by_id[cid]["clip"], m["frame"]) for m in by_id[cid]["members"]}

    remap = fold(labelled, min_signs)

    # track -> split, stratified so a thin class does not land entirely in val
    rng = random.Random(seed)
    by_class = collections.defaultdict(list)
    for cid, lab in labelled.items():
        by_class[remap[lab]].append(cid)
    split = {}
    for cids in by_class.values():
        cids = sorted(cids)
        rng.shuffle(cids)
        n_val = round(len(cids) * val_frac)
        split.update({c: ("val" if i < n_val else "train") for i, c in enumerate(cids)})

    raw = 0
    frames = collections.defaultdict(list)   # (clip, frame) -> [(cid, name, xyxy)]
    for cid, lab in labelled.items():
        t = by_id.get(cid)
        if not t:
            continue
        raw += len(t["members"])
        for d in sample(t["members"], step):
            fk = (t["clip"], d["frame"])
            if fk not in bad:
                frames[fk].append((cid, remap[lab], d["xyxy"]))

    # A frame can hold signs from two tracks. If those tracks fell on opposite
    # sides of the split there is no side the frame can go without leaking one
    # of them, so it is dropped. Counted, because a large number here would mean
    # the split is costing real data.
    keep, conflict = {}, 0
    for fk, items in frames.items():
        sides = {split[cid] for cid, _n, _b in items}
        if len(sides) == 1:
            keep[fk] = (sides.pop(), items)
        else:
            conflict += 1

    names = [n for n in classes.THAI_FINE_NAMES if n in by_class]
    return {
        "names": names, "idx": {n: i for i, n in enumerate(names)},
        "frames": keep, "split": split, "remap": remap, "by_class": by_class,
        "n_tracks": len(tracks), "n_signs": len(labelled),
        "n_blocked": len(blocked), "n_background": len(tracks) - len(key) - len(blocked & set(by_id) - set(key)),
        "raw": raw, "conflict": conflict, "bad_frames": len(bad),
    }


def report(p):
    boxes = [(n, s) for s, items in ((s, i) for s, i in p["frames"].values())
             for _c, n, _b in items]
    per_split = collections.Counter(s for s, _i in p["frames"].values())
    kept = sum(len(i) for _s, i in p["frames"].values())

    print(f"\n  {p['n_signs']} labelled signs   "
          f"{p['raw']} raw detections -> {kept} boxes on "
          f"{len(p['frames'])} frames   ({kept / max(p['n_signs'], 1):.1f}x per sign)")
    print(f"  frames: {per_split['train']} train / {per_split['val']} val"
          + (f"   ({p['conflict']} dropped: train+val signs share the frame)"
             if p["conflict"] else ""))
    print(f"  excluded: {p['n_blocked']} unnameable signs ({p['bad_frames']} frames), "
          f"{p['n_tracks'] - p['n_signs'] - p['n_blocked']} not_a_sign tracks kept as "
          f"unlabelled background\n")

    n_box = collections.Counter(n for n, _s in boxes)
    n_sign = {n: len(c) for n, c in p["by_class"].items()}
    n_val = {n: sum(p["split"][c] == "val" for c in cs) for n, cs in p["by_class"].items()}
    print(f"  {'class':<22} {'signs':>6} {'val':>4} {'boxes':>7}")
    for n in sorted(p["names"], key=lambda x: -n_box[x]):
        flag = "  <- no val signs, AP not meaningful" if not n_val[n] else ""
        print(f"  {n:<22} {n_sign[n]:>6} {n_val[n]:>4} {n_box[n]:>7}{flag}")

    folded = {a: b for a, b in p["remap"].items() if a != b}
    if folded:
        print(f"\n  folded (too few distinct signs): "
              + ", ".join(f"{a}->{b}" for a, b in sorted(folded.items())))


def extract(p, root, footage, out, width):
    import cv2  # only the extract path needs it; --report stays stdlib

    for s in ("train", "val"):
        for d in ("images", "labels"):
            (out / d / s).mkdir(parents=True, exist_ok=True)

    per_clip = collections.defaultdict(list)
    for (clip, fno), (side, items) in p["frames"].items():
        per_clip[clip].append((fno, side, items))

    done = 0
    for clip in sorted(per_clip):
        # rglob, so it does not matter whether clips sit in footages/ directly or
        # in footages/<batch>/ -- tracks.json records the clip name, not its path
        vid = next(iter(footage.rglob(f"{clip}.*")), None)
        if vid is None:
            print(f"  !! no video for {clip}, skipping {len(per_clip[clip])} frames")
            continue
        cap = cv2.VideoCapture(str(vid))
        for fno, side, items in sorted(per_clip[clip]):
            cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
            ok, img = cap.read()
            if not ok:
                continue
            H, W = img.shape[:2]
            if W > width:
                img = cv2.resize(img, (width, round(H * width / W)),
                                 interpolation=cv2.INTER_AREA)
            stem = f"{clip}_f{fno:06d}"
            cv2.imwrite(str(out / "images" / side / f"{stem}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            # coordinates are normalised, so the resize above needs no box maths
            (out / "labels" / side / f"{stem}.txt").write_text("".join(
                f"{p['idx'][n]} {((x1+x2)/2)/W:.6f} {((y1+y2)/2)/H:.6f} "
                f"{(x2-x1)/W:.6f} {(y2-y1)/H:.6f}\n"
                for _c, n, (x1, y1, x2, y2) in items))
            done += 1
        cap.release()
        print(f"  {clip}: {len(per_clip[clip])} frames")

    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\n\nnames:\n"
        + "".join(f"  {i}: {n}\n" for i, n in enumerate(p["names"])))
    print(f"\n  wrote {done} images -> {out}/   (data.yaml lists {len(p['names'])} classes)")


def selfcheck():
    m = [{"frame": f, "size": s, "xyxy": [0, 0, s, s]}
         for f, s in enumerate([10, 10.5, 11, 20, 20, 40, 41])]
    got = [d["size"] for d in sample(m, 0.2)]
    assert got == [10, 20, 40], got            # 10.5/11 are <20% from 10; 41 is <20% from 40
    assert [d["size"] for d in sample(m, 0.0)] == [10, 10.5, 11, 20, 20, 40, 41]
    assert sample([], 0.2) == []

    assert catch_all("Regulatory") == "other_regulatory"
    assert catch_all("Information") == "information", "Information has no other_* class"

    labels = {f"a{i}": "stop" for i in range(2)} | {f"b{i}": "speed_limit" for i in range(9)}
    r = fold(labels, min_signs=5)
    assert r["stop"] == "other_regulatory", r      # 2 signs -> folded
    assert r["speed_limit"] == "speed_limit", r    # 9 signs -> kept
    # a catch-all is never folded into itself, however thin it is
    assert fold({"x": "information"}, min_signs=99)["information"] == "information"
    print("ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", type=pathlib.Path, default=pathlib.Path("work/gold"))
    p.add_argument("--footage", type=pathlib.Path, default=pathlib.Path("footages"))
    p.add_argument("--out", type=pathlib.Path)
    p.add_argument("--report", action="store_true", help="print the numbers, write nothing")
    p.add_argument("--selfcheck", action="store_true")
    p.add_argument("--size-step", type=float, default=0.20,
                   help="keep a box once it has changed size by this fraction (0 = every frame)")
    p.add_argument("--val-frac", type=float, default=0.20)
    p.add_argument("--min-signs", type=int, default=5,
                   help="classes with fewer distinct signs fold into their catch-all")
    p.add_argument("--img-width", type=int, default=1280)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()

    if a.selfcheck:
        return selfcheck()
    if not a.out and not a.report:
        p.error("need --out or --report")

    plan_ = plan(a.dir, a.size_step, a.val_frac, a.min_signs, a.seed)
    report(plan_)
    if a.out:
        extract(plan_, a.dir, a.footage, a.out, a.img_width)


if __name__ == "__main__":
    main()
