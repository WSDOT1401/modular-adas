#!/usr/bin/env python3
"""[4] Group review in CVAT: send Qwen's answers out, bring the corrections back.

    python cvat.py export --tracks work/pass2/tracks.json --frames work/pass2/frames \
                          --pred work/predictions_v2.csv --out work/review_task.zip
    #   ... upload review_task.zip to a new CVAT task, your group fixes it, export
    #       the task as "YOLO 1.1" ...
    python cvat.py import --zip ~/Downloads/task_export.zip \
                          --tracks work/pass2/tracks.json --out work/reviewed.csv

Use this instead of ``sort.py`` review mode when your group reviews together, or
when the boxes themselves need fixing. ``sort.py`` is faster per crop but it can
only change the *label*; CVAT can also move the box, split one box into two, and
let several people work the same queue.

**Why boxes are worth fixing here.** Only the peak frame of each track is ever
seen by a human. ``propagate.py`` then copies that track's detector geometry onto
every other frame. A box fixed here is a box fixed on all ~6 frames that sign
contributes; a box left sloppy is sloppy ~6 times.

The round trip is by IoU against the peak box recorded in ``tracks.json``, so a
reviewer can nudge a box without breaking the link back to its sign. Three things
can happen to a box, and ``import`` reports all three:

  * matched   -> that sign's reviewed label (and corrected geometry)
  * deleted   -> the reviewer says it was never a sign; recorded as not_a_sign
  * added     -> a sign the detector missed. Counted, but NOT imported: it has no
                 track behind it, so there is nothing to propagate it along.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import shutil
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import classes  # noqa: E402

# A reviewer needs a word for every verdict, including "this is not a sign".
# Deleting the box would say the same thing, but silently -- and a missing box is
# indistinguishable from one nobody got to. An explicit label is a record that a
# human looked. Must match gold.py's SPECIAL so the two workflows agree.
SPECIAL = ("too_small", "dont_know", "not_a_sign", "composite")
NAMES = list(classes.THAI_FINE_NAMES) + list(SPECIAL)


def catch_all(parent: str) -> str:
    group = classes.THAI_FINE_BY_PARENT[parent]
    return next((o for o in group if o.startswith("other_")), group[-1])


def read_labels(path: pathlib.Path) -> dict[str, str]:
    """crop_id -> label, from either CSV shape in this pipeline.

    classify.py writes `pred`; gold.py's answer_key.csv writes `label`. Both are
    legitimate inputs for a review task, so read whichever is there rather than
    making the caller remember which file they are holding."""
    rows = list(csv.DictReader(path.open()))
    if not rows:
        return {}
    col = next((c for c in ("pred", "label") if c in rows[0]), None)
    if col is None:
        sys.exit(f"{path}: expected a 'pred' or 'label' column, got {list(rows[0])}")
    return {r["crop_id"]: r[col] for r in rows}


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / union if union > 0 else 0.0


def cmd_export(args):
    from PIL import Image  # only to read frame size; no decode of video needed

    tracks = [t for t in json.loads(args.tracks.read_text()) if t.get("crop_id")]
    pred = read_labels(args.pred) if args.pred and args.pred.exists() else {}

    idx = {n: i for i, n in enumerate(NAMES)}
    by_frame = collections.defaultdict(list)
    for t in tracks:
        # No prediction (or an unparseable one) falls back to the parent's
        # catch-all rather than being dropped: a box that is not in the task is a
        # sign nobody reviews, which is the one outcome worth avoiding.
        lab = pred.get(t["crop_id"], "")
        if lab not in idx:
            lab = catch_all(t["coarse"])
        by_frame[f"{t['clip']}_f{t['peak']['frame']:06d}"].append((lab, t["peak"]["xyxy"]))

    stage = args.out.with_suffix("")
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "obj_train_data").mkdir(parents=True)

    written, missing = 0, []
    for stem, boxes in sorted(by_frame.items()):
        src = args.frames / f"{stem}.jpg"
        if not src.exists():
            missing.append(stem)
            continue
        shutil.copy(src, stage / "obj_train_data" / src.name)
        W, H = Image.open(src).size
        (stage / "obj_train_data" / f"{stem}.txt").write_text("".join(
            f"{idx[l]} {((x1+x2)/2)/W:.6f} {((y1+y2)/2)/H:.6f} "
            f"{(x2-x1)/W:.6f} {(y2-y1)/H:.6f}\n" for l, (x1, y1, x2, y2) in boxes))
        written += 1

    (stage / "obj.names").write_text("\n".join(NAMES) + "\n")
    (stage / "obj.data").write_text(
        f"classes = {len(NAMES)}\ntrain = data/train.txt\n"
        "names = data/obj.names\nbackup = backup/\n")
    (stage / "train.txt").write_text("\n".join(
        f"data/obj_train_data/{s}.jpg" for s in sorted(by_frame) if s not in missing) + "\n")
    shutil.make_archive(str(stage), "zip", stage)
    shutil.rmtree(stage)

    n_pred = sum(1 for t in tracks if pred.get(t["crop_id"]) in idx)
    print(f"{args.out}: {written} frames, {sum(len(b) for b in by_frame.values())} boxes")
    print(f"  {n_pred} pre-filled from {args.pred}, "
          f"{len(tracks)-n_pred} fell back to their coarse catch-all")
    if missing:
        print(f"  !! {len(missing)} frames not found in {args.frames} — skipped")
    print(f"\nIn CVAT: new task -> upload this zip -> Import annotations -> "
          f"format 'YOLO 1.1'.\nLabels come from obj.names, so create the task "
          f"with those {len(NAMES)} labels.")


def cmd_import(args):
    from PIL import Image

    tracks = [t for t in json.loads(args.tracks.read_text()) if t.get("crop_id")]
    peaks = collections.defaultdict(list)
    for t in tracks:
        peaks[f"{t['clip']}_f{t['peak']['frame']:06d}"].append(t)

    rows, added, skipped = [], 0, 0
    with zipfile.ZipFile(args.zip) as z:
        members = {pathlib.PurePath(n).name: n for n in z.namelist()}
        # CVAT can reorder or extend the label list, so trust the exported
        # obj.names over our own ordering -- an off-by-one here would relabel
        # every box in the batch with no error reported anywhere.
        if "obj.names" not in members:
            sys.exit("no obj.names in the zip — is this a 'YOLO 1.1' export?")
        names = z.read(members["obj.names"]).decode().split()

        for stem, group in sorted(peaks.items()):
            txt = members.get(f"{stem}.txt")
            if txt is None:
                skipped += len(group)          # frame absent: nobody reviewed it
                continue
            # CVAT writes normalised coords; the frame on disk gives the size to
            # put tracks.json's pixel boxes into the same space.
            W, H = Image.open(args.frames / f"{stem}.jpg").size
            boxes = []
            for line in z.read(txt).decode().splitlines():
                if not line.strip():
                    continue
                c, cx, cy, w, h = (float(v) for v in line.split())
                boxes.append((names[int(c)], (cx-w/2, cy-h/2, cx+w/2, cy+h/2)))

            used = set()
            for t in group:
                x1, y1, x2, y2 = t["peak"]["xyxy"]
                mine = (x1/W, y1/H, x2/W, y2/H)
                best, score = None, 0.0
                for i, (_lab, b) in enumerate(boxes):
                    s = iou(mine, b)
                    if i not in used and s > score:
                        best, score = i, s
                if best is not None and score >= args.iou:
                    rows.append((t["crop_id"], boxes[best][0]))
                    used.add(best)
                else:
                    rows.append((t["crop_id"], "not_a_sign"))
            added += len(boxes) - len(used)

    with args.out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["crop_id", "label"])
        w.writerows(rows)

    dist = collections.Counter(l for _c, l in rows)
    gone = dist.get("not_a_sign", 0)
    print(f"{args.out}: {len(rows)} reviewed signs")
    print(f"  {len(rows)-gone} matched a reviewed box, {gone} deleted -> not_a_sign")
    print(f"  {added} boxes the reviewers ADDED (signs the detector missed) — "
          "not imported, they have no track to propagate along")
    if skipped:
        print(f"  !! {skipped} signs on frames missing from the export — NOT "
              "reviewed, and silently absent from the output. Check the task.")
    print("\nper-class:")
    for n, c in dist.most_common():
        print(f"  {n:26s} {c:4d}")
    print(f"\nNext: fold these into the gold workspace, then\n"
          f"  python gold.py score --dir work/gold --solo\n"
          f"  python propagate.py --out work/dataset")


def selfcheck():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((0, 0, 10, 10), (0, 0, 5, 10)) - 0.5) < 1e-9
    # A reviewer nudging or retightening a box must not break the link back to
    # its sign -- that would silently record the sign as not_a_sign. Both of
    # these must clear the --iou 0.3 default by a wide margin.
    assert iou((0, 0, 100, 100), (3, 3, 103, 103)) > 0.85     # shifted 3px
    assert iou((0, 0, 100, 100), (10, 10, 90, 90)) > 0.6      # tightened 10%
    # ...while a genuinely different sign nearby must NOT match
    assert iou((0, 0, 100, 100), (90, 0, 190, 100)) < 0.3
    assert catch_all("Information") == "information"
    assert "not_a_sign" in NAMES and NAMES[:len(classes.THAI_FINE_NAMES)] == \
        list(classes.THAI_FINE_NAMES), "fine classes must keep their index order"
    print("ok")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="predictions -> a CVAT-importable zip")
    e.add_argument("--tracks", type=pathlib.Path, required=True)
    e.add_argument("--frames", type=pathlib.Path, required=True)
    e.add_argument("--pred", type=pathlib.Path)
    e.add_argument("--out", type=pathlib.Path, default=pathlib.Path("work/review_task.zip"))
    e.set_defaults(fn=cmd_export)

    i = sub.add_parser("import", help="a CVAT 'YOLO 1.1' export -> reviewed labels")
    i.add_argument("--zip", type=pathlib.Path, required=True)
    i.add_argument("--tracks", type=pathlib.Path, required=True)
    i.add_argument("--out", type=pathlib.Path, default=pathlib.Path("work/reviewed.csv"))
    i.add_argument("--frames", type=pathlib.Path, required=True,
                   help="the same frames dir used for export — gives the frame size")
    i.add_argument("--iou", type=float, default=0.3,
                   help="below this a box counts as deleted, not moved")
    i.set_defaults(fn=cmd_import)

    sub.add_parser("selfcheck").set_defaults(fn=lambda _a: selfcheck())

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
