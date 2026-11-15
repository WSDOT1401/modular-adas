#!/usr/bin/env python3
"""Cut M2's real crops out of the M1 dataset, and split them by clip.

    python build_m2.py          # -> m2/{train,val}/<class>/*.jpg

Two gates, and both throw crops away on purpose:

  >= 24 px short side    below this a human cannot read the sign either, and M1
                         is trained not to emit boxes that small.
  not touching the edge   a half-sign at the frame border is a fine detection
                         target and a poison classification target -- the model
                         would learn to name signs from half their pixels.

The reject class is not padding. It is the two sets of negatives we already own:
every box a human DELETED in CVAT (precisely where M1 fires and is wrong), plus
random squares off the frames that hold no sign at all.

Synthetic crops are deliberately NOT written here -- m2_synth.py draws them
fresh at train time, so there is no fixed synthetic set to memorise. Val is real
crops only, always.

## The split

Still by clip, never by crop: one physical sign repeats across frames inside a
clip, so a crop-level split puts the same sign on both sides and inflates the
score. But M2 picks its own clips rather than inheriting M1's, for one measured
reason -- M1's split left **5 of the 13 displayed classes with no scoreable val
set** (left_curve 13 crops, all in train; no_right_turn 5, all in train). A
blank cell in the presentation is the one failure a split can prevent.

Two rules, in order:

1. **Every clip M1 held out stays held out.** M2's val is a superset of M1's, so
   a clip is never in M1's val and M2's train at the same time, and an
   end-to-end demo on an M1 val clip is honest for both models.
2. **Then buy coverage for the 13 displayed classes**, rarest first, until each
   has --min-val real crops or has run out of clips. This costs train real
   crops of exactly the classes that have infinite synthetic ones, which is the
   cheapest thing we own. `information` is the exception and needs no help: 354
   crops across 46 clips.
"""
import argparse
import collections
import csv
import random
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent / "autolabel" / "dataset"
BATCHES = HERE.parent / "autolabel" / "batches"

sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402

NAMES = classes.THAI_FINE_NAMES
DISPLAYED = classes.THAI_FINE_DISPLAYED
REJECT = "not_a_sign"           # the 29th class: "dash stays quiet"
READABLE = 24                   # source px, short side -- M1's val floor
SIZE = 128                      # see m2_synth.py: 64 is the trap
EDGE = 2                        # px from the border before we call a box clipped


def square(im, x1, y1, x2, y2):
    """Box -> square crop around its centre, clamped to the frame.

    Square because degrade() composites onto a square canvas. Training on
    stretched rectangles and testing on squares is a free way to lose points.
    """
    half = min(max(x2 - x1, y2 - y1) / 2, im.width / 2, im.height / 2)
    cx = min(max((x1 + x2) / 2, half), im.width - half)
    cy = min(max((y1 + y2) / 2, half), im.height - half)
    return im.crop((round(cx - half), round(cy - half),
                    round(cx + half), round(cy + half))).resize(
                        (SIZE, SIZE), Image.LANCZOS)


def clip_of():
    """frame_id -> clip, from the batch manifests.

    Not from the filename: b01 frames are named 2026_0912_013522_f004680, so
    splitting on "_" gives the wrong clip for a whole batch.
    """
    m = {}
    for d in sorted(BATCHES.glob("*")):
        f = d / "manifest.csv"
        if f.exists():
            with f.open() as fh:
                m.update({r["frame_id"]: r["clip"] for r in csv.DictReader(fh)})
    assert m, f"no manifests under {BATCHES}"
    return m


def collect(skipped):
    """Every usable crop in the M1 dataset, both of M1's splits.

    Returns (crops, frames-with-no-signs). A crop is
    (frame_path, clip, class, (x1, y1, x2, y2), key).
    """
    clips = clip_of()
    crops, empty, m1_val = [], [], set()
    for split in ("train", "val"):
        for img in sorted((DATASET / "images" / split).glob("*.jpg")):
            clip = clips[img.stem]
            if split == "val":
                m1_val.add(clip)
            lab = DATASET / "labels" / split / f"{img.stem}.txt"
            lines = [l for l in (lab.read_text().splitlines() if lab.exists() else []) if l.strip()]
            if not lines:
                empty.append((img, clip))
                continue
            W, H = Image.open(img).size
            for i, line in enumerate(lines):
                p = line.split()
                if len(p) < 5:
                    continue
                xc, yc, bw, bh = (float(v) for v in p[1:5])
                x1, y1 = (xc - bw / 2) * W, (yc - bh / 2) * H
                x2, y2 = (xc + bw / 2) * W, (yc + bh / 2) * H
                name = NAMES[int(p[0])]
                if min(x2 - x1, y2 - y1) < READABLE:
                    skipped[f"{name}: too small"] += 1
                elif x1 < EDGE or y1 < EDGE or x2 > W - EDGE or y2 > H - EDGE:
                    skipped[f"{name}: clipped by frame edge"] += 1
                else:
                    crops.append((img, clip, name, (x1, y1, x2, y2), f"{img.stem}_{i}"))

    # The boxes a human deleted in CVAT. M1 proposed them at conf 0.15 and was
    # wrong -- the best negatives we will ever get for free. No edge gate here:
    # a sign-shaped nothing at the frame border is still nothing.
    where = {p.stem: p for s in ("train", "val")
             for p in (DATASET / "images" / s).glob("*.jpg")}
    for d in sorted(BATCHES.glob("*")):
        f = d / "reviewed.csv"
        if not f.exists():
            continue
        with f.open() as fh:
            for i, r in enumerate(csv.DictReader(fh)):
                img = where.get(r["frame_id"])
                if r["label"] != REJECT or img is None:
                    continue
                box = tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2"))
                if min(box[2] - box[0], box[3] - box[1]) < READABLE:
                    skipped[f"{REJECT}: too small"] += 1
                    continue
                crops.append((img, clips[img.stem], REJECT, box, f"{img.stem}_del{i}"))
    return crops, empty, m1_val


def choose_val(crops, m1_val, min_val):
    """Which clips go to val. Rule 1 then rule 2 -- see the module docstring."""
    per_clip = collections.defaultdict(collections.Counter)
    for _img, clip, name, _box, _key in crops:
        per_clip[clip][name] += 1
    total = collections.Counter()
    for h in per_clip.values():
        total.update(h)

    val = set(m1_val)
    for name in sorted(DISPLAYED, key=lambda n: total[n]):
        got = sum(per_clip[c][name] for c in val)
        while got < min(min_val, total[name]):
            left = [c for c in per_clip if c not in val and per_clip[c][name]]
            if not left:
                break
            # most of this class, and among ties the clip that drags the least
            # else across with it
            pick = max(left, key=lambda c: (per_clip[c][name], -sum(per_clip[c].values())))
            val.add(pick)
            got += per_clip[pick][name]
    return val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m2")
    ap.add_argument("--min-val", type=int, default=5,
                    help="real val crops to buy for each displayed class")
    ap.add_argument("--per-bg", type=int, default=2,
                    help="reject crops cut from each frame that holds no sign")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    out, rng = Path(a.out), random.Random(a.seed)
    skipped = collections.Counter()
    crops, empty, m1_val = collect(skipped)
    val = choose_val(crops, m1_val, a.min_val)

    # Random squares off the sign-free frames, sized from the same distribution
    # degrade() uses -- otherwise "reject" quietly becomes the class of small
    # blurry things.
    for img, clip in empty:
        W, H = Image.open(img).size
        for i in range(a.per_bg):
            s = max(26, min(150, int(rng.lognormvariate(3.85, 0.40))))
            x, y = rng.randint(0, W - s), rng.randint(0, H - s)
            crops.append((img, clip, REJECT, (x, y, x + s, y + s), f"{img.stem}_bg{i}"))

    for split in ("train", "val"):
        for name in list(NAMES) + [REJECT]:
            (out / split / name).mkdir(parents=True, exist_ok=True)

    counts, opened = collections.Counter(), (None, None)
    for img, clip, name, box, key in sorted(crops, key=lambda c: c[0]):
        if opened[0] != img:
            opened = (img, Image.open(img))
        split = "val" if clip in val else "train"
        square(opened[1], *box).save(out / split / name / f"{key}.jpg", quality=92)
        counts[split, name] += 1

    # The split's whole contract, checked against the data every run.
    assert m1_val <= val, "a clip M1 held out ended up in M2's train set"
    for name in DISPLAYED:
        n = counts["train", name] + counts["val", name]
        assert counts["val", name] >= min(a.min_val, n), f"{name}: split left it unscoreable"

    hdr = f"{'class':24s} {'train':>6s} {'val':>5s}"
    print(f"{hdr}\n{'-' * len(hdr)}")
    for name in list(NAMES) + [REJECT]:
        t, v = counts["train", name], counts["val", name]
        mark = ("  <- shown, NOT SCORED" if name in DISPLAYED and v < a.min_val
                else "  *" if name in DISPLAYED else "")
        print(f"{name:24s} {t:6d} {v:5d}{mark}")
    t = sum(c for (s, _), c in counts.items() if s == "train")
    v = sum(c for (s, _), c in counts.items() if s == "val")
    print(f"{'-' * len(hdr)}\n{'TOTAL':24s} {t:6d} {v:5d}   ({v / (t + v):.0%} val)")
    print(f"\n{len(val)} val clips ({len(m1_val)} inherited from M1), "
          f"{len({c for _i, c, _n, _b, _k in crops}) - len(val)} train clips")
    print(f"dropped {sum(skipped.values())} crops:")
    for reason, n in skipped.most_common(6):
        print(f"  {n:5d}  {reason}")
    print(f"\n* = shown on the dash. {len(NAMES) + 1} classes -> {out.resolve()}")
    print("Val is real only. Synthetic comes from m2_synth.py at train time.")


if __name__ == "__main__":
    main()
