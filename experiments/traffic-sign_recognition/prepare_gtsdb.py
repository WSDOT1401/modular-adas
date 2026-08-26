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

# Suffixes ultralytics reads directly (subset of its IMG_FORMATS, 8.4.69). An
# image already in one of these is reused as-is — the whole point of converting
# is that ultralytics cannot read PPM, so re-encoding a PNG would be pure waste.
READABLE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
# Everything we accept as a source image. Mirrors of GTSDB variously ship the
# original .ppm or an already-converted .png/.jpg.
SOURCE_SUFFIXES = READABLE_SUFFIXES | {".ppm", ".pgm", ".pnm"}


def find_gtsdb_candidates(root: pathlib.Path) -> list[pathlib.Path]:
    """Every directory beneath ``root`` holding a ``gt.txt``, shallowest first.

    A Kaggle Dataset may be uploaded flat, wrapped in ``FullIJCNN2013/``, or split
    into ``TrainIJCNN2013/`` + ``TestIJCNN2013/`` — hence the search. Returns all
    matches so the caller can say which one it used and which it ignored; picking
    one silently is how a whole split goes missing.
    """
    matches = sorted(root.rglob("gt.txt"), key=lambda p: (len(p.parts), str(p)))
    if not matches:
        raise FileNotFoundError(f"no gt.txt found anywhere under {root}")
    return [m.parent for m in matches]


def parse_gt(gt_path: pathlib.Path) -> dict[str, list[tuple[int, int, int, int, int]]]:
    """Parse ``gt.txt`` into ``{stem: [(left, top, right, bottom, class_id)]}``.

    Lines are ``filename;left;top;right;bottom;classId`` — semicolon separated,
    no header. Images with no sign simply do not appear.

    Keyed by *stem*, not filename: mirrors that re-encode the images to PNG
    usually leave ``gt.txt`` still naming ``.ppm``, so matching on the full
    filename would silently find zero annotations.
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
        boxes[pathlib.Path(name).stem].append(tuple(int(n) for n in nums))  # type: ignore[arg-type]
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


def _resolve_sources(
    gtsdb_root: pathlib.Path,
    train_dir: str | pathlib.Path | None,
    val_dir: str | pathlib.Path | None,
) -> tuple[list[tuple[str | None, pathlib.Path]], list[pathlib.Path]]:
    """Work out where images come from and how they map to splits.

    Two modes:

    * **explicit** — ``train_dir`` / ``val_dir`` name one directory per split
      (relative to ``gtsdb_root``, or absolute). Split comes from *directory
      membership*, which is the only thing that works when a redistribution
      ships ``TrainIJCNN2013/`` + ``TestIJCNN2013/`` and numbers both from
      00000.
    * **single directory** — one ``gt.txt`` with all 900 images; split comes
      from the filename index (the official IJCNN 2013 rule).

    Returns ``([(split_or_None, image_dir)], all_gt_txt_dirs)``.
    """
    if bool(train_dir) != bool(val_dir):
        raise ValueError("--train-dir and --val-dir must be given together")

    if train_dir is not None:
        sources: list[tuple[str | None, pathlib.Path]] = []
        for split, raw in (("train", train_dir), ("val", val_dir)):
            path = pathlib.Path(raw)
            path = path if path.is_absolute() else gtsdb_root / path
            if not (path / "gt.txt").exists():
                raise FileNotFoundError(f"no gt.txt in {path} (needed for the {split} split)")
            sources.append((split, path))
        return sources, [d for _, d in sources]

    candidates = find_gtsdb_candidates(gtsdb_root)
    chosen = candidates[0]
    if len(candidates) > 1:
        print(f"  NOTE: {len(candidates)} directories contain a gt.txt. Reading only:")
        print(f"    -> {chosen}")
        for other in candidates[1:]:
            print(f"       ignoring {other}")
    return [(None, chosen)], candidates


def _collect_records(
    sources: list[tuple[str | None, pathlib.Path]]
) -> list[tuple[str, int, pathlib.Path, list[tuple[int, int, int, int, int]]]]:
    """Flatten the sources into ``[(split, index, ppm_path, boxes)]``.

    Each source directory carries its own ``gt.txt``. Images absent from it keep
    an empty box list — they become background negatives, not dropped rows.
    """
    records = []
    for split_override, image_dir in sources:
        annotations = parse_gt(image_dir / "gt.txt")
        images = sorted(
            path for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
        )
        for image in images:
            try:
                index = int(image.stem)
            except ValueError:
                print(f"  skipping non-numeric filename {image.name}", file=sys.stderr)
                continue
            split = split_override or split_for(index)
            records.append((split, index, image, annotations.get(image.stem, [])))
    if not records:
        searched = ", ".join(str(d) for _, d in sources)
        found = sorted({
            path.suffix.lower() or "(no extension)"
            for _, d in sources for path in d.iterdir() if path.is_file()
        })
        raise FileNotFoundError(
            f"no usable images found in {searched}\n"
            f"  file types present: {', '.join(found) or 'none'}\n"
            f"  accepted: {', '.join(sorted(SOURCE_SUFFIXES))}\n"
            "  If the images sit in a subdirectory next to gt.txt, point "
            "--train-dir/--val-dir (or --gtsdb-root) at the directory holding them."
        )
    return records


def _cache_images(records, cache_dir: pathlib.Path):
    """Materialise each source image under ``<cache>/<split>/`` exactly once.

    Returns ``([(split, index, cached_path, width, height, boxes)], n_converted)``.

    An image already in a format ultralytics reads is hardlinked, not re-encoded
    — mirrors that ship PNG have done the work already. Only PPM (and friends)
    get converted, to PNG rather than JPEG because some signs are 16 px across
    and JPEG ringing on a 16 px box is a real cost.

    Pillow rather than cv2: ``Image.open`` reads only the header, so sizes are
    free and an already-cached image is never touched twice.
    """
    entries = []
    converted = 0
    for split in SPLITS:
        (cache_dir / split).mkdir(parents=True, exist_ok=True)

    for split, index, source, boxes in records:
        reusable = source.suffix.lower() in READABLE_SUFFIXES
        suffix = source.suffix.lower() if reusable else ".png"
        cached = cache_dir / split / f"{index:05d}{suffix}"

        with Image.open(source) as im:
            width, height = im.size          # header only
            if not cached.exists():
                if reusable:
                    _place(source, cached)
                else:
                    im.convert("RGB").save(cached)
                    converted += 1
        entries.append((split, index, cached, width, height, boxes))
    return entries, converted


def _place(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Hardlink ``src`` to ``dst``, copying if the filesystem refuses."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _link_images(dataset_dir: pathlib.Path, entries) -> None:
    """Populate ``<dataset>/images/<split>/`` with hardlinks into the cache.

    Hardlinks rather than a symlinked directory on purpose — see the module
    docstring.
    """
    for split in SPLITS:
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
    for split, _index, cached, _w, _h, _boxes in entries:
        dst = dataset_dir / "images" / split / cached.name
        if not dst.exists():
            _place(cached, dst)


def _empty_split_message(
    empty: list[str], records, sources, candidates: list[pathlib.Path], explicit: bool
) -> str:
    """Explain an empty split here, where the cause is still visible.

    Without this the run continues and ultralytics dies much later on
    "No images found in .../images/val", which points at the symptom rather than
    the dataset layout that caused it.
    """
    indices = sorted(entry[1] for entry in records)
    lines = [
        f"GTSDB conversion produced an empty {'/'.join(empty)} split — stopping now, "
        "because training would otherwise fail later inside ultralytics with a "
        '"No images found" error that does not explain why.',
        "",
        f"Read {len(records)} images from:",
        *(f"  {d}" for _, d in sources),
        f"  filename indices: {indices[0]:05d}..{indices[-1]:05d}",
    ]
    if explicit:
        lines += ["", "One of --train-dir / --val-dir contains no .ppm images."]
        return "\n".join(lines)

    lines.append(f"  split rule: index < {TRAIN_SPLIT_END} -> train, else val")
    if len(candidates) > 1:
        lines += [
            "",
            f"This dataset has {len(candidates)} directories containing a gt.txt, and only "
            "the first was read:",
            *(f"  {'-> ' if c == sources[0][1] else '   '}{c}" for c in candidates),
            "",
            "That layout ships train and test as separate directories, each numbered "
            "from 00000, so the index rule cannot tell them apart. Re-run with, e.g.:",
            "",
            "  --train-dir TrainIJCNN2013 --val-dir TestIJCNN2013",
        ]
    else:
        lines += [
            "",
            "This looks like only part of GTSDB — the full benchmark is 900 images, "
            "00000..00899. Point --gtsdb-root at a directory holding all of them, or "
            "pass --train-dir / --val-dir to split by directory instead.",
        ]
    return "\n".join(lines)


def prepare(
    gtsdb_root: pathlib.Path,
    out: pathlib.Path,
    label_set: str,
    train_dir: str | pathlib.Path | None = None,
    val_dir: str | pathlib.Path | None = None,
) -> dict:
    """Build ``<out>/gtsdb-<label_set>/`` and return a summary of what was written."""
    gtsdb_root, out = pathlib.Path(gtsdb_root), pathlib.Path(out)
    names, mapping = classes.label_set(label_set)

    sources, candidates = _resolve_sources(gtsdb_root, train_dir, val_dir)
    records = _collect_records(sources)

    cache_dir = out / "_images"
    entries, converted = _cache_images(records, cache_dir)

    dataset_dir = out / f"gtsdb-{label_set}"
    labels_root = dataset_dir / "labels"
    if labels_root.exists():
        shutil.rmtree(labels_root)      # never mix label sets or stale mappings
    for split in SPLITS:
        (labels_root / split).mkdir(parents=True)

    stats = {s: {"images": 0, "boxes": 0, "negatives": 0} for s in SPLITS}
    histogram: collections.Counter[str] = collections.Counter()
    dropped = 0

    for split, index, _cached, width, height, boxes in sorted(entries, key=lambda e: (e[0], e[1])):
        rows = []
        for box in boxes:
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
        (labels_root / split / f"{index:05d}.txt").write_text(
            "\n".join(rows) + ("\n" if rows else "")
        )
        stats[split]["images"] += 1
        stats[split]["boxes"] += len(rows)
        if not rows:
            stats[split]["negatives"] += 1

    empty = [split for split in SPLITS if stats[split]["images"] == 0]
    if empty:
        raise ValueError(
            _empty_split_message(empty, entries, sources, candidates, train_dir is not None)
        )

    _link_images(dataset_dir, entries)

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
        "sources": [str(d) for _, d in sources],
        "splits": stats,
        "histogram": dict(histogram),
        "dropped": dropped,
        "converted": converted,
    }


def _print_summary(summary: dict) -> None:
    print(f"\n  {summary['label_set']}  ->  {summary['dataset_dir']}")
    for source in summary["sources"]:
        print(f"  source: {source}")
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
    parser.add_argument("--train-dir", default=None,
                        help="split by directory instead of filename index; give both "
                             "--train-dir and --val-dir (relative to --gtsdb-root, or absolute). "
                             "Needed when a dataset ships TrainIJCNN2013/ + TestIJCNN2013/.")
    parser.add_argument("--val-dir", default=None, help="see --train-dir")
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parent / "datasets",
                        help="where to write the YOLO dataset(s)")
    args = parser.parse_args(argv)
    try:
        summary = prepare(args.gtsdb_root, args.out, args.label_set,
                          train_dir=args.train_dir, val_dir=args.val_dir)
    except (ValueError, FileNotFoundError) as exc:
        # These are dataset-layout problems, not crashes — a traceback just
        # buries the explanation.
        print(f"\nERROR: {exc}\n", file=sys.stderr)
        return 2
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
