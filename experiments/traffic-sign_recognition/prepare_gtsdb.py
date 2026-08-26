"""Convert GTSDB into a YOLO dataset (one per label set).

GTSDB ships 900 images as ``NNNNN.ppm`` (1360x800) plus a single ``gt.txt``.
Two things force a conversion step rather than pointing YOLO at it directly:

1. ``.ppm`` is not in ultralytics' ``IMG_FORMATS`` (checked against 8.4.69), so
   the pixels have to be re-encoded. PNG, not JPEG — some signs are 16 px across
   and JPEG ringing on a 16 px box is a real cost.
2. ``ultralytics/data/utils.py:img2label_paths`` finds labels by replacing
   ``/images/`` with ``/labels/``, i.e. labels must be a *sibling* of images. Two
   label sets therefore need two directory trees.

They do not need two copies of the pixels, though. Images are decoded once into
``<out>/_images/<split>/`` and each label set's ``images/<split>`` is filled with
*hardlinks* to them — saves ~1.3 GB and makes the second label set nearly free.

Hardlinks specifically, not a symlinked directory: ``check_det_dataset`` resolves
symlinks, which rewrites the split path to ``_images/<split>`` and sends
``img2label_paths`` hunting for a non-existent ``_labels/``. Every image then
loads as a background negative and training silently learns nothing. A hardlink
is indistinguishable from a real file, so there is nothing to resolve away.

Split is the official IJCNN 2013 one: index < 600 -> train, else val. Note that
val therefore doubles as the test set, so early stopping makes the reported
number mildly optimistic; that is the standard GTSDB protocol and keeps our mAP
comparable to published results.

Usage::

    python3 prepare_gtsdb.py --gtsdb-root /kaggle/input/<slug> --label-set 4class
"""
from __future__ import annotations

import argparse
import collections
import os
import pathlib
import shutil
import sys

from PIL import Image

import classes

# Official IJCNN 2013 split point: images 00000..00599 train, 00600..00899 val.
TRAIN_SPLIT_END = 600
SPLITS = ("train", "val")


def find_gtsdb_dir(root: pathlib.Path) -> pathlib.Path:
    """Locate the directory holding ``gt.txt`` beneath ``root``.

    A Kaggle Dataset may be uploaded flat or with the original
    ``FullIJCNN2013/`` wrapper, so search rather than assume a layout.
    """
    matches = sorted(root.rglob("gt.txt"))
    if not matches:
        raise FileNotFoundError(f"no gt.txt found anywhere under {root}")
    return matches[0].parent


def parse_gt(gt_path: pathlib.Path) -> dict[str, list[tuple[int, int, int, int, int]]]:
    """Parse ``gt.txt`` into ``{filename: [(left, top, right, bottom, class_id)]}``.

    Lines are ``filename;left;top;right;bottom;classId`` — semicolon separated,
    no header. Images with no sign simply do not appear.
    """
    boxes: dict[str, list[tuple[int, int, int, int, int]]] = collections.defaultdict(list)
    for lineno, raw in enumerate(gt_path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) != 6:
            raise ValueError(f"{gt_path}:{lineno}: expected 6 fields, got {len(parts)}: {line!r}")
        name, *nums = parts
        boxes[name].append(tuple(int(n) for n in nums))  # type: ignore[arg-type]
    return dict(boxes)


def split_for(index: int) -> str:
    return "train" if index < TRAIN_SPLIT_END else "val"


def _to_yolo(
    box: tuple[int, int, int, int, int], width: int, height: int
) -> tuple[int, float, float, float, float] | None:
    """Clamp a GTSDB box to the frame and normalise it, or ``None`` if degenerate.

    GTSDB gives pixel edges; we take width as ``right - left`` (the near-universal
    convention — the alternative ``+ 1`` differs by one pixel on a ~50 px box).
    """
    left, top, right, bottom, class_id = box
    left, top = max(0, left), max(0, top)
    right, bottom = min(width, right), min(height, bottom)
    box_w, box_h = right - left, bottom - top
    if box_w <= 0 or box_h <= 0:
        return None
    return (
        class_id,
        (left + right) / 2 / width,
        (top + bottom) / 2 / height,
        box_w / width,
        box_h / height,
    )


def _cache_images(image_dir: pathlib.Path, cache_dir: pathlib.Path) -> tuple[dict[int, tuple[int, int]], int]:
    """Decode every ``NNNNN.ppm`` to ``<cache>/<split>/NNNNN.png`` once.

    Returns ``({index: (width, height)}, n_converted)``. Pillow rather than cv2
    because ``Image.open`` reads only the header, so sizes are free on re-runs
    and an already-converted image is never re-encoded.
    """
    sizes: dict[int, tuple[int, int]] = {}
    converted = 0
    for split in SPLITS:
        (cache_dir / split).mkdir(parents=True, exist_ok=True)

    for ppm in sorted(image_dir.glob("*.ppm")):
        try:
            index = int(ppm.stem)
        except ValueError:
            print(f"  skipping non-numeric filename {ppm.name}", file=sys.stderr)
            continue
        png = cache_dir / split_for(index) / f"{ppm.stem}.png"
        with Image.open(ppm) as im:
            sizes[index] = im.size
            if not png.exists():
                im.convert("RGB").save(png)
                converted += 1
    if not sizes:
        raise FileNotFoundError(f"no .ppm images found in {image_dir}")
    return sizes, converted


def _link_images(dataset_dir: pathlib.Path, cache_dir: pathlib.Path, indices: list[int]) -> None:
    """Populate ``<dataset>/images/<split>/`` with hardlinks into the PNG cache.

    Hardlinks rather than a symlinked directory on purpose — see the module
    docstring. Falls back to copying if the filesystem refuses (e.g. the cache
    and dataset land on different devices).
    """
    for split in SPLITS:
        target = dataset_dir / "images" / split
        target.mkdir(parents=True, exist_ok=True)
    for index in indices:
        split = split_for(index)
        src = cache_dir / split / f"{index:05d}.png"
        dst = dataset_dir / "images" / split / f"{index:05d}.png"
        if dst.exists():
            continue
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)


def prepare(gtsdb_root: pathlib.Path, out: pathlib.Path, label_set: str) -> dict:
    """Build ``<out>/gtsdb-<label_set>/`` and return a summary of what was written."""
    gtsdb_root, out = pathlib.Path(gtsdb_root), pathlib.Path(out)
    names, mapping = classes.label_set(label_set)

    image_dir = find_gtsdb_dir(gtsdb_root)
    annotations = parse_gt(image_dir / "gt.txt")

    cache_dir = out / "_images"
    sizes, converted = _cache_images(image_dir, cache_dir)

    dataset_dir = out / f"gtsdb-{label_set}"
    labels_root = dataset_dir / "labels"
    if labels_root.exists():
        shutil.rmtree(labels_root)      # never mix label sets or stale mappings
    for split in SPLITS:
        (labels_root / split).mkdir(parents=True)

    stats = {s: {"images": 0, "boxes": 0, "negatives": 0} for s in SPLITS}
    histogram: collections.Counter[str] = collections.Counter()
    dropped = 0

    for index in sorted(sizes):
        split = split_for(index)
        width, height = sizes[index]
        rows = []
        for box in annotations.get(f"{index:05d}.ppm", []):
            converted_box = _to_yolo(box, width, height)
            if converted_box is None:
                dropped += 1
                continue
            gtsdb_id, cx, cy, bw, bh = converted_box
            if gtsdb_id not in mapping:
                print(f"  dropping out-of-range class id {gtsdb_id}", file=sys.stderr)
                dropped += 1
                continue
            cls = mapping[gtsdb_id]
            histogram[names[cls]] += 1
            rows.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        # An empty .txt is meaningful: ultralytics reads it as a background image.
        # Omitting these would inflate precision by never testing false positives.
        (labels_root / split / f"{index:05d}.txt").write_text("\n".join(rows) + ("\n" if rows else ""))
        stats[split]["images"] += 1
        stats[split]["boxes"] += len(rows)
        if not rows:
            stats[split]["negatives"] += 1

    _link_images(dataset_dir, cache_dir, sorted(sizes))

    data_yaml = dataset_dir / "data.yaml"
    data_yaml.write_text(
        "# Generated by prepare_gtsdb.py — do not edit by hand.\n"
        f"path: {dataset_dir.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"names: [{', '.join(names)}]\n"
    )

    return {
        "label_set": label_set,
        "dataset_dir": str(dataset_dir),
        "data_yaml": str(data_yaml),
        "splits": stats,
        "histogram": dict(histogram),
        "dropped": dropped,
        "converted": converted,
    }


def _print_summary(summary: dict) -> None:
    print(f"\n  {summary['label_set']}  ->  {summary['dataset_dir']}")
    print(f"  PNGs encoded this run: {summary['converted']}  (rest served from cache)")
    for split, s in summary["splits"].items():
        print(
            f"  {split:5s}  {s['images']:4d} images  {s['boxes']:4d} boxes  "
            f"{s['negatives']:4d} background"
        )
    total = sum(summary["histogram"].values())
    print(f"  boxes by class ({total} total, {summary['dropped']} dropped):")
    for name, count in sorted(summary["histogram"].items(), key=lambda kv: -kv[1]):
        print(f"    {name:14s} {count:4d}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gtsdb-root", required=True, type=pathlib.Path,
                        help="dir containing gt.txt and *.ppm (searched recursively)")
    parser.add_argument("--label-set", default="4class", choices=classes.LABEL_SETS)
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parent / "datasets",
                        help="where to write the YOLO dataset(s)")
    args = parser.parse_args(argv)
    _print_summary(prepare(args.gtsdb_root, args.out, args.label_set))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
