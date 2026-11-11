#!/usr/bin/env python3
"""Post-export label fixes: drop 8 notice-board boxes, reclassify 1.

Patches BOTH the YOLO label files and the COCO json so the two exports stay in
agreement (``audit2.py`` checks this).

Boxes are identified by their **normalised centre**, not by their position in
the file. Two reasons:

* The CVAT export's annotation order agrees with the YOLO file order for most
  but not all images (54/427 disagreed when this was written), so an index
  would silently hit the wrong box in the COCO json.
* It makes the script idempotent and re-export-safe — a box that is already
  gone simply matches nothing.

NOT a CVAT operation: a fresh CVAT export undoes all 9 edits. Re-run this after
every export, or make the same changes in CVAT and delete this script. See
``thai-traffic-sign-labs/README.md``.

Usage::

    python3 fix_labels.py            # apply (idempotent)
    python3 fix_labels.py --check    # report only, change nothing
"""
from __future__ import annotations

import argparse
import json
import pathlib

DATASETS = pathlib.Path(__file__).resolve().parent.parent / "datasets"
LBL = DATASETS / "YOLO/labels/train"
COCO = DATASETS / "COCO/annotations/instances_default.json"

# Match tolerance on the normalised centre. Boxes within one image are far
# further apart than this, and the YOLO export rounds to 6 decimals.
TOL = 2e-3

# Every one of these is the red header strip of a red-over-yellow Thai roadside
# notice board -- not an official traffic sign. Boxing only the strip teaches
# "red horizontal rectangle = Regulatory sign", which fires on shop banners.
DELETE = [
    ("2026_0912_012925_f001275", 0.524952, 0.537353),
    ("2026_0912_012925_f001350", 0.480456, 0.463264),
    ("2026_0912_013224_f005025", 0.492318, 0.541906),
    ("2026_0912_020728_f000150", 0.432517, 0.509495),
    ("2026_0912_022224_f001050", 0.394297, 0.486894),
    ("2026_0912_022224_f004050", 0.352372, 0.495340),
    ("2026_0912_022224_f005025", 0.439555, 0.523796),
    ("2026_0912_022821_f002625", 0.385994, 0.489946),
]
# Blue circular mandatory sign: Information -> Regulatory.
RECLASS = [("2026_0912_012925_f002850", 0.307303, 0.469468, 0)]

# COCO category ids are 1-based, ordered Regulatory/Warning/Information.
YOLO_TO_COCO_CAT = {0: 1, 1: 2, 2: 3}


def _action(stem: str, cx: float, cy: float) -> int | None | str:
    """``"delete"``, a target class id, or ``None`` if this box is untouched."""
    for s, x, y in DELETE:
        if s == stem and abs(x - cx) < TOL and abs(y - cy) < TOL:
            return "delete"
    for s, x, y, cls in RECLASS:
        if s == stem and abs(x - cx) < TOL and abs(y - cy) < TOL:
            return cls
    return None


def patch_yolo(apply: bool) -> tuple[int, int]:
    dropped = reclassed = 0
    stems = {s for s, *_ in DELETE} | {s for s, *_ in RECLASS}
    for stem in sorted(stems):
        path = LBL / f"{stem}.txt"
        if not path.exists():
            raise SystemExit(f"missing label file: {path}")
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        out, changed = [], False
        for line in lines:
            parts = line.split()
            action = _action(stem, float(parts[1]), float(parts[2]))
            if action == "delete":
                dropped += 1
                changed = True
                continue
            if action is not None and int(parts[0]) != action:
                line = " ".join([str(action), *parts[1:]])
                reclassed += 1
                changed = True
            out.append(line)
        if changed and apply:
            path.write_text("".join(f"{l}\n" for l in out))
    return dropped, reclassed


def patch_coco(apply: bool) -> tuple[int, int]:
    doc = json.loads(COCO.read_text())
    dims = {im["id"]: (pathlib.Path(im["file_name"]).stem, im["width"], im["height"])
            for im in doc["images"]}

    keep, dropped, reclassed = [], 0, 0
    for ann in doc["annotations"]:
        stem, W, H = dims[ann["image_id"]]
        x, y, w, h = ann["bbox"]
        action = _action(stem, (x + w / 2) / W, (y + h / 2) / H)
        if action == "delete":
            dropped += 1
            continue
        if action is not None:
            want = YOLO_TO_COCO_CAT[action]
            if ann["category_id"] != want:
                reclassed += 1
            ann["category_id"] = want
        keep.append(ann)
    if (dropped or reclassed) and apply:
        doc["annotations"] = keep
        COCO.write_text(json.dumps(doc) + "\n")
    return dropped, reclassed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    args = parser.parse_args(argv)
    apply = not args.check

    yd, yr = patch_yolo(apply)
    cd, cr = patch_coco(apply)
    verb = "would drop" if args.check else "dropped"
    print(f"YOLO: {verb} {yd}, reclassed {yr}")
    print(f"COCO: {verb} {cd}, reclassed {cr}")
    if (yd, yr) != (cd, cr):
        raise SystemExit("YOLO and COCO disagree on what needs patching — investigate")
    if not any((yd, yr)):
        print("nothing to do — fixes already applied")

    total = sum(1 for p in LBL.glob("*.txt") for l in p.read_text().splitlines() if l.strip())
    print(f"YOLO boxes now: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
