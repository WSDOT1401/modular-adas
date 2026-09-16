#!/usr/bin/env python3
"""Merge the per-session CVAT exports under ``thai-traffic-sign-dataset/`` into one
COCO dataset and one YOLO dataset.

Labelling happens in sessions -- one person, one day, one zip per format. That is the
right unit for handing work around and the wrong unit for training, so this flattens
every session into a single dataset per format.

Three things about the real exports drive the code:

* **Layouts drift.** Images sit at ``images/`` in some zips and ``images/train/`` in
  others, one session capitalised ``Train`` (folder *and* ``instances_Train.json``),
  the folder inside a zip does not always match the zip's name, and every zip carries
  macOS ``__MACOSX``/``.DS_Store`` litter. Nothing here matches a fixed path -- files
  are found by what they are.
* **Class names drift, indices do not.** ``Regulatory`` in one session is
  ``regulartory`` in another. The order is identical in both, so the label files are
  already compatible and only the names need normalising. Each zip's own name list is
  still checked against :data:`CLASS_NAMES` rather than trusted, because a genuinely
  reordered export would otherwise relabel the merged dataset in silence.
* **Two exports disagree with themselves.** An annotation entry whose jpg is not in
  the zip is dropped along with its boxes, because a COCO ``file_name`` pointing at a
  missing file crashes most loaders. A jpg the annotations never mention is kept as a
  background negative instead, which is what it is.

Everything written lives under ``COCO/`` and ``YOLO/``; the source tree is read-only.
Both output trees are rebuilt from scratch on every run, so this is safe to re-run and
cannot leave a stale file from an earlier run sitting in the merged dataset.

    ./extractor.py --verify
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import shutil
import sys
import zipfile

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SPLIT = "train"                    # every export so far is one undivided train split
ANNOTATION_FILE = "instances_default.json"

CLASS_NAMES = ["Regulatory", "Warning", "Information"]
# One annotator's exports say "regulartory" -- a typo for the first name, same class,
# same index. Resolving names through this table rather than by position is what would
# catch an export whose classes were genuinely reordered.
ALIASES = {"regulatory": 0, "regulartory": 0, "warning": 1, "information": 2}


def _fail(message: str):
    raise SystemExit(f"extractor: {message}")


def _members(archive: zipfile.ZipFile):
    """Every real file in the archive, macOS litter dropped.

    ``__MACOSX/`` holds AppleDouble twins of each file -- same name under ``._`` --
    so a plain suffix match would otherwise find two of everything.
    """
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        parts = pathlib.PurePosixPath(name).parts
        if any(p == "__MACOSX" or p == ".DS_Store" or p.startswith("._") for p in parts):
            continue
        yield name


def _pictures(names) -> dict[str, str]:
    """``basename -> member`` for every image, wherever in the zip it happens to sit."""
    found = {}
    for name in names:
        path = pathlib.PurePosixPath(name)
        if path.suffix.lower() in IMAGE_SUFFIXES:
            found[path.name] = name
    return found


def _split_of(name: str, anchor: str) -> str | None:
    """The split directory in ``.../<anchor>/<split>/file``, or None when flat."""
    path = pathlib.PurePosixPath(name)
    lowered = [part.lower() for part in path.parts]
    if anchor in lowered:
        index = lowered.index(anchor)
        if index + 2 < len(path.parts):
            return path.parts[index + 1]
    return None


def _extract(archive: zipfile.ZipFile, member: str, dest: pathlib.Path):
    with archive.open(member) as source, open(dest, "wb") as handle:
        shutil.copyfileobj(source, handle)


def _class_index(name: str, where: str) -> int:
    key = name.strip().lower()
    if key not in ALIASES:
        _fail(f"{where}: unknown class {name!r}. Add it to ALIASES (and to CLASS_NAMES "
              "if it is genuinely new) -- merging it blind would corrupt the labels.")
    return ALIASES[key]


def _fresh(path: pathlib.Path):
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)


# --------------------------------------------------------------------------- COCO


def _coco_document(archive, names, zip_path) -> dict:
    """The one annotations json in the zip. Its name varies (``instances_Train.json``
    in one session), so it is found by living under ``annotations/``, not by name."""
    found = [n for n in names
             if n.lower().endswith(".json") and "annotations" in n.lower().split("/")]
    if len(found) != 1:
        _fail(f"{zip_path.name}: expected one annotations json, found {len(found)}")
    return json.loads(archive.read(found[0]).decode("utf-8"))


def merge_coco(zip_paths, out_dir: pathlib.Path, warn) -> list[tuple]:
    images_dir, annotations_dir = out_dir / "images", out_dir / "annotations"
    _fresh(images_dir)
    _fresh(annotations_dir)

    merged = {
        "licenses": [{"name": "", "id": 0, "url": ""}],
        "info": {"contributor": "", "date_created": "", "url": "", "version": "",
                 "year": "", "description": "Thai traffic signs, merged from CVAT "
                                            "session exports by extractor.py"},
        "categories": [{"id": index + 1, "name": name, "supercategory": ""}
                       for index, name in enumerate(CLASS_NAMES)],
        "images": [], "annotations": [],
    }
    seen, rows = {}, []
    next_image = next_annotation = 1

    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            names = list(_members(archive))
            pictures = _pictures(names)
            for base in sorted(pictures):
                if base in seen:
                    warn(f"{zip_path.name}: {base} already came from {seen[base]}; "
                         "skipped rather than silently overwritten")
                    del pictures[base]
                else:
                    seen[base] = zip_path.name

            document = _coco_document(archive, names, zip_path)
            categories = {c["id"]: _class_index(c["name"], zip_path.name) + 1
                          for c in document["categories"]}

            listed, remap = set(), {}
            for image in document["images"]:
                base = pathlib.PurePosixPath(image["file_name"]).name
                listed.add(base)
                if base not in pictures:
                    continue           # annotated, but the jpg never made it into the zip
                remap[image["id"]] = next_image
                merged["images"].append({**image, "id": next_image, "file_name": base})
                next_image += 1

            boxes = 0
            for annotation in document["annotations"]:
                if annotation["image_id"] not in remap:
                    continue
                merged["annotations"].append({
                    **annotation, "id": next_annotation,
                    "image_id": remap[annotation["image_id"]],
                    "category_id": categories[annotation["category_id"]]})
                next_annotation += 1
                boxes += 1

            # CVAT's plain-YOLO exporter silently drops rotated shapes -- the format
            # is axis-aligned and cannot hold one -- so COCO/ legitimately ends up with
            # more boxes than YOLO/. Counted here so that gap is never a mystery.
            rotated = sum(1 for a in document["annotations"]
                          if a["image_id"] in remap
                          and (a.get("attributes") or {}).get("rotation"))
            if rotated:
                warn(f"{zip_path.name}: {rotated} box(es) carry a rotation. The COCO bbox "
                     "is the un-rotated rect either way, so the geometry is fine, but "
                     "CVAT's YOLO export can be missing them -- the box-count check below "
                     "is what says whether it is.")

            # A jpg the json never mentions is still a real background negative -- the
            # YOLO export keeps it as one, so listing it here keeps both datasets over
            # the same images.
            # ponytail: its size is copied from the rest of the zip rather than decoded
            # from the file. Every session is frames from one clip, so one size per zip
            # (verified across all eight); decode for real if a mixed-resolution
            # session ever turns up.
            extras = sorted(set(pictures) - listed)
            sizes = collections.Counter((i["width"], i["height"]) for i in document["images"])
            if extras and not sizes:
                warn(f"{zip_path.name}: {len(extras)} unannotated image(s) and no "
                     "annotated one to take a frame size from; left out of COCO")
                extras = []
            for base in extras:
                (width, height), _ = sizes.most_common(1)[0]
                merged["images"].append({"id": next_image, "width": width, "height": height,
                                         "file_name": base, "license": 0, "flickr_url": "",
                                         "coco_url": "", "date_captured": 0})
                next_image += 1

            for base, member in sorted(pictures.items()):
                _extract(archive, member, images_dir / base)

            gone = sorted(listed - set(pictures))
            if gone:
                warn(f"{zip_path.name}: {len(gone)} annotated image(s) are missing from "
                     f"the zip, dropped with their boxes: {', '.join(gone[:4])}"
                     f"{' ...' if len(gone) > 4 else ''}")
            rows.append((zip_path.name, len(pictures), boxes, len(extras), len(gone)))

    (annotations_dir / ANNOTATION_FILE).write_text(json.dumps(merged, indent=2) + "\n")
    rows.append(("total", len(merged["images"]), len(merged["annotations"]),
                 sum(r[3] for r in rows), sum(r[4] for r in rows)))
    return rows


# --------------------------------------------------------------------------- YOLO


def _yaml_names(text: str, where: str) -> dict[int, str]:
    """Pull the ``names:`` block out of a CVAT ``data.yaml`` without a yaml dependency.

    The block is always ``names:`` followed by indented ``<index>: <name>`` lines, so
    a two-state line scan covers it -- and anything else raises rather than quietly
    agreeing with a file it did not understand.
    """
    names, inside = {}, False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():
            inside = line.split(":", 1)[0].strip().lower() == "names"
            continue
        if inside:
            key, _, value = line.strip().partition(":")
            try:
                names[int(key)] = value.strip()
            except ValueError:
                _fail(f"{where}: cannot read {line.strip()!r} as a class index")
    return names


def _class_remap(archive, names, zip_path, warn) -> dict[int, int]:
    """This zip's class index -> the merged dataset's class index."""
    found = [n for n in names if pathlib.PurePosixPath(n).name.lower() == "data.yaml"]
    if not found:
        warn(f"{zip_path.name}: no data.yaml, so its class order cannot be checked; "
             "assuming the canonical one")
        return {index: index for index in range(len(CLASS_NAMES))}
    declared = _yaml_names(archive.read(found[0]).decode("utf-8"), zip_path.name)
    return {index: _class_index(name, zip_path.name) for index, name in declared.items()}


def _relabel(text: str, remap: dict[int, int], where: str, warn) -> str:
    """Rewrite a label file's class column into canonical order.

    The coordinates pass through as the exact strings the exporter wrote -- only the
    class column is touched -- so this is lossless whatever precision CVAT chose.
    """
    kept = []
    for number, line in enumerate(text.splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 5:
            warn(f"{where}:{number}: expected 5 fields, got {len(parts)}; line dropped")
            continue
        try:
            parts[0] = str(remap[int(parts[0])])
        except (ValueError, KeyError):
            warn(f"{where}:{number}: class {parts[0]!r} is not in that export's own "
                 "name list; line dropped")
            continue
        kept.append(" ".join(parts))
    return "".join(line + "\n" for line in kept)


def merge_yolo(zip_paths, out_dir: pathlib.Path, warn) -> list[tuple]:
    images_dir, labels_dir = out_dir / "images" / SPLIT, out_dir / "labels" / SPLIT
    _fresh(images_dir)
    _fresh(labels_dir)

    seen, rows = {}, []
    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            names = list(_members(archive))
            pictures = _pictures(names)
            for base in sorted(pictures):
                if base in seen:
                    warn(f"{zip_path.name}: {base} already came from {seen[base]}; "
                         "skipped rather than silently overwritten")
                    del pictures[base]
                else:
                    seen[base] = zip_path.name

            for name in names:
                split = _split_of(name, "images") or _split_of(name, "labels")
                if split and split.lower() != SPLIT:
                    warn(f"{zip_path.name}: split {split!r} folded into {SPLIT!r}")
                    break

            labels = {}
            for name in names:
                path = pathlib.PurePosixPath(name)
                if path.suffix.lower() == ".txt" and "labels" in [
                        part.lower() for part in path.parts[:-1]]:
                    labels[path.stem] = name

            remap = _class_remap(archive, names, zip_path, warn)

            boxes = empty = 0
            for base, member in sorted(pictures.items()):
                _extract(archive, member, images_dir / base)
                stem = pathlib.PurePosixPath(base).stem
                text = archive.read(labels[stem]).decode("utf-8") if stem in labels else ""
                # An image with no .txt is a background negative, and YOLO only reads it
                # as one if the empty file is actually there. Leaving it out instead
                # would quietly inflate precision.
                body = _relabel(text, remap, f"{zip_path.name}:{stem}.txt", warn)
                (labels_dir / f"{stem}.txt").write_text(body)
                boxes += len(body.splitlines())
                empty += not body

            orphans = sorted(set(labels) - {pathlib.PurePosixPath(b).stem for b in pictures})
            if orphans:
                warn(f"{zip_path.name}: {len(orphans)} label file(s) have no image in "
                     f"the zip, dropped: {', '.join(orphans[:4])}"
                     f"{' ...' if len(orphans) > 4 else ''}")
            rows.append((zip_path.name, len(pictures), boxes, empty, len(orphans)))

    out_dir.joinpath("data.yaml").write_text(
        "path: .\n"
        f"train: images/{SPLIT}\n"
        "names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASS_NAMES)))
    # Kept because every source export shipped one; data.yaml above is what ultralytics
    # actually reads.
    out_dir.joinpath(f"{SPLIT}.txt").write_text(
        "".join(f"images/{SPLIT}/{base}\n" for base in sorted(seen)))

    rows.append(("total", sum(r[1] for r in rows), sum(r[2] for r in rows),
                 sum(r[3] for r in rows), sum(r[4] for r in rows)))
    return rows


# ------------------------------------------------------------------------- verify


def verify(coco_dir: pathlib.Path, yolo_dir: pathlib.Path) -> list[str]:
    """Re-read what was written and report everything wrong with it."""
    problems = []

    document = json.loads((coco_dir / "annotations" / ANNOTATION_FILE).read_text())
    on_disk = {p.name for p in (coco_dir / "images").iterdir()
               if p.suffix.lower() in IMAGE_SUFFIXES}
    listed = {image["file_name"] for image in document["images"]}
    problems += [f"COCO: {name} is in the json but not in images/"
                 for name in sorted(listed - on_disk)]
    problems += [f"COCO: {name} is in images/ but not in the json"
                 for name in sorted(on_disk - listed)]

    image_ids = [image["id"] for image in document["images"]]
    if len(image_ids) != len(set(image_ids)):
        problems.append("COCO: duplicate image ids")
    annotation_ids = [a["id"] for a in document["annotations"]]
    if len(annotation_ids) != len(set(annotation_ids)):
        problems.append("COCO: duplicate annotation ids")
    known, categories = set(image_ids), {c["id"] for c in document["categories"]}
    for annotation in document["annotations"]:
        if annotation["image_id"] not in known:
            problems.append(f"COCO: annotation {annotation['id']} points at missing "
                            f"image {annotation['image_id']}")
        if annotation["category_id"] not in categories:
            problems.append(f"COCO: annotation {annotation['id']} has unknown category "
                            f"{annotation['category_id']}")

    images = {p.stem for p in (yolo_dir / "images" / SPLIT).iterdir()
              if p.suffix.lower() in IMAGE_SUFFIXES}
    labels = {p.stem for p in (yolo_dir / "labels" / SPLIT).glob("*.txt")}
    problems += [f"YOLO: {stem} has no label file" for stem in sorted(images - labels)]
    problems += [f"YOLO: {stem}.txt has no image" for stem in sorted(labels - images)]

    lines = 0
    for path in sorted((yolo_dir / "labels" / SPLIT).glob("*.txt")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            parts = line.split()
            if not parts:
                continue
            lines += 1
            where = f"YOLO: {path.name}:{number}"
            if len(parts) != 5:
                problems.append(f"{where}: {len(parts)} fields, expected 5")
                continue
            try:
                index, box = int(parts[0]), [float(p) for p in parts[1:]]
            except ValueError:
                problems.append(f"{where}: {line!r} is not numeric")
                continue
            if not 0 <= index < len(CLASS_NAMES):
                problems.append(f"{where}: class {index} outside 0..{len(CLASS_NAMES) - 1}")
            if any(not 0.0 <= value <= 1.0 for value in box):
                problems.append(f"{where}: {box} is not normalised to 0..1")

    if set(images) != {pathlib.PurePosixPath(n).stem for n in listed}:
        problems.append("COCO and YOLO do not cover the same images")
    # The two formats describe the same boxes, so the counts must agree. A rotated
    # shape in CVAT is what usually breaks this: its plain-YOLO exporter drops those.
    if len(document["annotations"]) != lines:
        problems.append(f"COCO has {len(document['annotations'])} boxes but YOLO has "
                        f"{lines}; check the rotation warnings above")
    return problems


# --------------------------------------------------------------------------- main


def _table(title: str, columns, rows):
    print(f"\n{title}")
    widths = [max(len(str(row[i])) for row in [columns, *rows]) for i in range(len(columns))]
    for row in [columns, *rows]:
        cells = [str(cell).ljust(widths[0]) if i == 0 else str(cell).rjust(widths[i])
                 for i, cell in enumerate(row)]
        line = "  " + "  ".join(cells)
        print(line)
        if row is columns or row[0] == "total":
            print("  " + "-" * (len(line) - 2))


def _under(root: pathlib.Path, value: str) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    return path if path.is_absolute() else root / path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge the CVAT session exports into one COCO and one YOLO dataset.")
    parser.add_argument("--source", default="thai-traffic-sign-dataset",
                        help="tree of <date>/<name>/*.zip to read (default: %(default)s)")
    parser.add_argument("--out", default=".",
                        help="where COCO/ and YOLO/ are written (default: alongside this script)")
    parser.add_argument("--verify", action="store_true",
                        help="re-read the merged output afterwards and check it")
    args = parser.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parent
    source, out = _under(root, args.source), _under(root, args.out)
    if not source.is_dir():
        _fail(f"{source} is not a directory")

    warnings = []
    def warn(message):
        warnings.append(message)

    coco_zips, yolo_zips = [], []
    for path in sorted(source.rglob("*.zip")):
        stem = path.stem.upper()
        if stem.endswith("-COCO"):
            coco_zips.append(path)
        elif stem.endswith("-YOLO"):
            yolo_zips.append(path)
        else:
            warn(f"{path.name}: ends in neither -COCO nor -YOLO; skipped")
    if not coco_zips and not yolo_zips:
        _fail(f"no -COCO or -YOLO zips under {source}")
    print(f"{len(coco_zips)} COCO and {len(yolo_zips)} YOLO exports under "
          f"{source.relative_to(root) if source.is_relative_to(root) else source}")

    coco_rows = merge_coco(coco_zips, out / "COCO", warn) if coco_zips else []
    yolo_rows = merge_yolo(yolo_zips, out / "YOLO", warn) if yolo_zips else []

    if coco_rows:
        _table("COCO/", ("export", "images", "boxes", "unlisted", "missing"), coco_rows)
    if yolo_rows:
        _table("YOLO/", ("export", "images", "boxes", "negatives", "orphans"), yolo_rows)

    if warnings:
        print(f"\n{len(warnings)} warning(s)")
        for message in warnings:
            print(f"  ! {message}")

    if not args.verify:
        return 0
    problems = verify(out / "COCO", out / "YOLO")
    if not problems:
        print("\nverify: OK")
        return 0
    print(f"\nverify: {len(problems)} problem(s)")
    for message in problems[:20]:
        print(f"  x {message}")
    if len(problems) > 20:
        print(f"  ... and {len(problems) - 20} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
