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
import json
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


def images_in(directory: pathlib.Path) -> list[pathlib.Path]:
    """Usable source images directly inside ``directory`` (not recursive)."""
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
    )


def image_dirs_under(root: pathlib.Path, limit: int = 12) -> list[str]:
    """``"<dir>  (N images)"`` for every directory beneath ``root`` holding images.

    Only used to make failures self-diagnosing: when no ``gt.txt`` directory has
    images, this says where they actually are.
    """
    counts: collections.Counter[pathlib.Path] = collections.Counter()
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
            counts[path.parent] += 1
    return [f"{d}  ({n} images)" for d, n in sorted(counts.items())[:limit]]


def find_gtsdb_candidates(root: pathlib.Path) -> list[pathlib.Path]:
    """Directories beneath ``root`` holding a ``gt.txt``, best candidate first.

    A Kaggle Dataset may be uploaded flat, wrapped in ``FullIJCNN2013/``, or
    split into ``TrainIJCNN2013/`` + ``TestIJCNN2013/`` — hence the search.

    **Directories that actually contain images sort first.** Mirrors commonly
    keep a stray ``gt.txt`` at the dataset root while the images live a level
    down with their own copy; taking the shallowest match lands on a directory
    with no images in it at all. Ties break on depth, then path, so the flat and
    wrapped layouts still resolve exactly as before.

    Returns every match so the caller can report what it ignored — choosing
    silently is how a whole split goes missing.
    """
    matches = sorted(root.rglob("gt.txt"), key=lambda p: (len(p.parts), str(p)))
    if not matches:
        raise FileNotFoundError(f"no gt.txt found anywhere under {root}")
    return sorted(
        (m.parent for m in matches),
        key=lambda d: (0 if images_in(d) else 1, len(d.parts), str(d)),
    )


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


def split_for(index: int, split_at: int = TRAIN_SPLIT_END) -> str:
    """Which split a filename index belongs to.

    Contiguous by index, never random: GTSDB frames come from continuous driving
    video, so shuffling would put near-duplicate consecutive frames on both
    sides of the split and inflate mAP into meaninglessness.
    """
    return "train" if index < split_at else "val"


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
        print(f"    -> {chosen}  ({len(images_in(chosen))} images)")
        for other in candidates[1:]:
            print(f"       ignoring {other}  ({len(images_in(other))} images)")
    return [(None, chosen)], candidates


def _collect_records(
    sources: list[tuple[str | None, pathlib.Path]], search_root: pathlib.Path,
    split_at: int = TRAIN_SPLIT_END,
) -> list[tuple[str, int, pathlib.Path, list[tuple[int, int, int, int, int]]]]:
    """Flatten the sources into ``[(split, index, ppm_path, boxes)]``.

    Each source directory carries its own ``gt.txt``. Images absent from it keep
    an empty box list — they become background negatives, not dropped rows.

    ``search_root`` is only used to make a failure self-diagnosing: if no source
    directory has images, it is scanned to report where they actually are. It
    must be the user-supplied root, never its parent, or the hint wanders off
    into unrelated directories on the machine.
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
            split = split_override or split_for(index, split_at)
            records.append((split, index, image, annotations.get(image.stem, [])))
    if not records:
        searched = ", ".join(str(d) for _, d in sources)
        found = sorted({
            path.suffix.lower() or "(no extension)"
            for _, d in sources for path in d.iterdir() if path.is_file()
        })
        elsewhere = image_dirs_under(search_root)
        lines = [
            f"no usable images found in {searched}",
            f"  file types present: {', '.join(found) or 'none'}",
            f"  accepted: {', '.join(sorted(SOURCE_SUFFIXES))}",
        ]
        if elsewhere:
            lines += [
                "",
                "  Images ARE present elsewhere in this dataset:",
                *(f"    {entry}" for entry in elsewhere),
                "",
                "  Point --gtsdb-root at the directory holding them (it needs a gt.txt "
                "beside the images), or pass --train-dir/--val-dir.",
            ]
        else:
            lines.append(
                "  No images anywhere under this dataset — check the attached Dataset."
            )
        raise FileNotFoundError("\n".join(lines))
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

    Rebuilt from scratch each run, exactly like ``labels/``. Merely adding what
    is missing leaves images from a previous ``--split-at`` still linked under
    their old split, so the same frame appears in train *and* val and the
    resulting mAP is meaningless.
    """
    images_root = dataset_dir / "images"
    if images_root.exists():
        shutil.rmtree(images_root)
    for split in SPLITS:
        (images_root / split).mkdir(parents=True)
    for split, _index, cached, _w, _h, _boxes in entries:
        dst = dataset_dir / "images" / split / cached.name
        if not dst.exists():
            _place(cached, dst)


def _empty_split_message(
    empty: list[str], entries, sources, candidates: list[pathlib.Path], explicit: bool,
    split_at: int = TRAIN_SPLIT_END,
) -> str:
    """Explain an empty split here, where the cause is still visible.

    Without this the run continues and ultralytics dies much later on
    "No images found in .../images/val", which points at the symptom rather than
    the dataset layout that caused it.
    """
    indices = sorted(entry[1] for entry in entries)
    lines = [
        f"GTSDB conversion produced an empty {'/'.join(empty)} split — stopping now, "
        "because training would otherwise fail later inside ultralytics with a "
        '"No images found" error that does not explain why.',
        "",
        f"Read {len(entries)} images from:",
        *(f"  {d}" for _, d in sources),
        f"  filename indices: {indices[0]:05d}..{indices[-1]:05d}",
    ]
    if explicit:
        lines += ["", "One of --train-dir / --val-dir contains no .ppm images."]
        return "\n".join(lines)

    lines.append(f"  split rule: index < {split_at} -> train, else val")
    suggested = max(1, int(len(indices) * 0.8))
    lines += [
        "",
        "Pick whichever fits your dataset:",
        "",
        f"  1. Only the train set is annotated. GTSDB's original competition release",
        f"     withheld the test ground truth, so a faithful mirror has 600 labelled",
        f"     images and 300 unlabelled ones. Carve a val split out of the labelled",
        f"     images (contiguous tail, so consecutive frames do not leak):",
        "",
        f"       --split-at {suggested}",
        "",
        "  2. Train and test ship as separate directories and BOTH have a gt.txt:",
        "",
        "       --train-dir <train subdir> --val-dir <test subdir>",
        "",
        "  3. A directory holds all 900 images with a gt.txt covering them (the",
        "     post-competition FullIJCNN2013 release): point --gtsdb-root at it and",
        "     keep the default --split-at 600.",
    ]
    if len(candidates) > 1:
        lines += [
            "",
            f"This dataset has {len(candidates)} directories containing a gt.txt, and only "
            "the first was read:",
            *(f"  {'-> ' if c == sources[0][1] else '   '}{c}" for c in candidates),
        ]
    else:
        pass
    return "\n".join(lines)


def prepare(
    gtsdb_root: pathlib.Path,
    out: pathlib.Path,
    label_set: str,
    train_dir: str | pathlib.Path | None = None,
    val_dir: str | pathlib.Path | None = None,
    split_at: int = TRAIN_SPLIT_END,
) -> dict:
    """Build ``<out>/gtsdb-<label_set>/`` and return a summary of what was written.

    ``split_at`` moves the train/val boundary. The default 600 is the official
    IJCNN 2013 split, valid only when all 900 annotated images are present. The
    original competition release withheld the test ground truth, so a faithful
    mirror has just the 600 labelled train images — there, pass a smaller value
    (e.g. 480) to carve a val split out of what is annotated.
    """
    gtsdb_root, out = pathlib.Path(gtsdb_root), pathlib.Path(out)
    names, mapping = classes.label_set(label_set)

    sources, candidates = _resolve_sources(gtsdb_root, train_dir, val_dir)
    records = _collect_records(sources, gtsdb_root, split_at)

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
            _empty_split_message(
                empty, entries, sources, candidates, train_dir is not None, split_at
            )
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

    # Recorded beside the dataset so report.py can state the split that was
    # actually used, instead of asserting the official one.
    dataset_meta = dataset_dir / "dataset_meta.json"
    dataset_meta.write_text(json.dumps({
        "label_set": label_set,
        "names": names,
        "split_at": split_at,
        "official_split": split_at == TRAIN_SPLIT_END,
        "sources": [str(d) for _, d in sources],
        "splits": stats,
        "histogram": dict(histogram),
        "dropped": dropped,
    }, indent=2) + "\n")

    return {
        "label_set": label_set,
        "split_at": split_at,
        "official_split": split_at == TRAIN_SPLIT_END,
        "dataset_meta": str(dataset_meta),
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
    print(f"  split at index: {summary['split_at']}")
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
    parser.add_argument("--split-at", type=int, default=TRAIN_SPLIT_END,
                        help=f"filename index where val begins (default {TRAIN_SPLIT_END}, the "
                             "official IJCNN 2013 split). Lower it when only the train set is "
                             "annotated, e.g. --split-at 480 for an 80/20 split of 600 images.")
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parent / "datasets",
                        help="where to write the YOLO dataset(s)")
    args = parser.parse_args(argv)
    try:
        summary = prepare(args.gtsdb_root, args.out, args.label_set,
                          train_dir=args.train_dir, val_dir=args.val_dir,
                          split_at=args.split_at)
    except (ValueError, FileNotFoundError) as exc:
        # These are dataset-layout problems, not crashes — a traceback just
        # buries the explanation.
        print(f"\nERROR: {exc}\n", file=sys.stderr)
        return 2
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
