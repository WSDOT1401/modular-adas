"""Split the hand-annotated Thai sign set into train/val/test and build it for YOLO.

The 330 frames are **not** 330 independent samples — they are 30 dashcam
recordings sliced into frames. Frames from one recording share roads, lighting
and often the same physical sign, so a random per-image split validates the
model on roads it has already memorised. Every split here is therefore grouped
by **clip** (the filename prefix before ``_f<frame>``).

Two modes, so the split is decided once and then reproduced identically
everywhere:

``--plan``
    Search clip assignments for a 70/20/10 split whose *per-class instance*
    share is closest to target, and write ``thai_splits.json``. Commit that
    file — it is the experiment's reproducibility record.

(default)
    Read ``thai_splits.json`` and materialise
    ``datasets/thai3/{images,labels}/{train,val,test}`` plus ``data.yaml``.
    Also writes ``data_f25/f50/f75.yaml`` for the data-scaling sweep; those
    share the *same* val and test directories and vary only ``train:``.

Usage::

    python3 prepare_thai.py --plan          # decide the split (once)
    python3 prepare_thai.py                 # build it (every machine)
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import random
import re
import shutil

import classes

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_SOURCE = HERE / "thai-traffic-sign-labs" / "datasets" / "YOLO"
SPLITS_JSON = HERE / "thai_splits.json"
LABEL_SET = "thai3"
SPLITS = ("train", "val", "test")
TARGET = {"train": 0.70, "val": 0.20, "test": 0.10}
# Nested subsets for the scaling sweep: f25 clips are a prefix of f50, and so
# on. Without nesting, the curve measures *which* clips as much as how many.
FRACTIONS = (25, 50, 75)

CLIP_RE = re.compile(r"^(.*)_f\d+$")


def clip_of(stem: str) -> str:
    match = CLIP_RE.match(stem)
    if not match:
        raise ValueError(
            f"{stem!r} does not match <clip>_f<frame> — the split is grouped by "
            "clip, and an unparseable name would silently become its own group"
        )
    return match.group(1)


def read_source(source: pathlib.Path) -> tuple[dict, dict]:
    """Return ``({stem: [class_id, ...]}, {clip: [stem, ...]})``."""
    images = {p.stem: p for p in (source / "images" / "train").iterdir()
              if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and not p.name.startswith(".")}
    labels = {p.stem: p for p in (source / "labels" / "train").glob("*.txt")}
    missing = sorted(set(images) - set(labels))
    if missing:
        raise SystemExit(f"{len(missing)} image(s) have no label file, e.g. {missing[:5]}")

    per_image, by_clip = {}, collections.defaultdict(list)
    for stem in sorted(images):
        per_image[stem] = [int(line.split()[0])
                           for line in labels[stem].read_text().splitlines() if line.strip()]
        by_clip[clip_of(stem)].append(stem)
    return per_image, dict(by_clip)


# --------------------------------------------------------------------------- plan


def plan(source: pathlib.Path, seed: int, iterations: int) -> dict:
    per_image, by_clip = read_source(source)
    n_classes = len(classes.label_set(LABEL_SET)[0])

    counts = {clip: [0] * n_classes for clip in by_clip}
    for stem, ids in per_image.items():
        for cid in ids:
            counts[clip_of(stem)][cid] += 1
    totals = [sum(counts[c][i] for c in counts) for i in range(n_classes)]

    # Clips holding no boxes at all are deliberate negatives. Spreading them
    # round-robin keeps every split's background ratio comparable; letting the
    # search place them would just add noise, since they move no class counts.
    labelled = sorted(c for c in by_clip if sum(counts[c]))
    empty = sorted(c for c in by_clip if not sum(counts[c]))

    n_val = max(1, round(len(labelled) * TARGET["val"]))
    n_test = max(1, round(len(labelled) * TARGET["test"]))

    rng = random.Random(seed)
    best = None
    for _ in range(iterations):
        shuffled = labelled[:]
        rng.shuffle(shuffled)
        groups = {"val": shuffled[:n_val],
                  "test": shuffled[n_val:n_val + n_test],
                  "train": shuffled[n_val + n_test:]}
        error = 0.0
        for cid in range(n_classes):
            if not totals[cid]:
                continue
            for name in SPLITS:
                share = sum(counts[c][cid] for c in groups[name]) / totals[cid]
                error += abs(share - TARGET[name])
        if best is None or error < best[0]:
            best = (error, {k: list(v) for k, v in groups.items()})

    _, groups = best
    for i, clip in enumerate(empty):
        groups[SPLITS[i % len(SPLITS)]].append(clip)
    for name in SPLITS:
        groups[name].sort()

    # Fixed order for nested sweep subsets, taken once so f25 ⊂ f50 ⊂ f75.
    sweep_order = groups["train"][:]
    random.Random(seed).shuffle(sweep_order)

    return {
        "label_set": LABEL_SET,
        "names": classes.label_set(LABEL_SET)[0],
        "seed": seed,
        "grouped_by": "clip (filename prefix before _f<frame>)",
        "clips": {name: groups[name] for name in SPLITS},
        "sweep_order": sweep_order,
        "fractions": list(FRACTIONS) + [100],
    }


# -------------------------------------------------------------------------- build


def _place(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Hardlink ``src`` to ``dst``, copying if the filesystem refuses."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _validate(manifest: dict, by_clip: dict) -> dict[str, list[str]]:
    """Resolve clips to image stems, refusing anything that would leak."""
    clips = manifest["clips"]
    seen: dict[str, str] = {}
    for name in SPLITS:
        for clip in clips[name]:
            if clip in seen:
                raise SystemExit(
                    f"clip {clip!r} is in both {seen[clip]} and {name} — that leaks "
                    "the same road into train and eval, which is the one thing this "
                    "script exists to prevent"
                )
            seen[clip] = name
    unassigned = sorted(set(by_clip) - set(seen))
    if unassigned:
        raise SystemExit(f"clips missing from thai_splits.json: {unassigned}")

    stems = {name: sorted(s for clip in clips[name] for s in by_clip[clip]) for name in SPLITS}
    for name in SPLITS:
        if not stems[name]:
            raise SystemExit(f"the {name} split is empty — refusing to write it")
    return stems


def build(source: pathlib.Path, out: pathlib.Path, manifest: dict) -> dict:
    per_image, by_clip = read_source(source)
    stems = _validate(manifest, by_clip)
    names, _ = classes.label_set(LABEL_SET)

    # Rebuilt from scratch: merely topping up leaves frames from an older split
    # still linked under their previous name, so one frame lands in two splits.
    for sub in ("images", "labels"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
        for split in SPLITS:
            (out / sub / split).mkdir(parents=True)

    src_img = source / "images" / "train"
    src_lbl = source / "labels" / "train"
    for split in SPLITS:
        for stem in stems[split]:
            image = next(p for p in src_img.glob(f"{stem}.*") if p.suffix.lower() != ".txt")
            _place(image, out / "images" / split / image.name)
            _place(src_lbl / f"{stem}.txt", out / "labels" / split / f"{stem}.txt")

    def tally(subset: list[str]) -> dict:
        per_class = collections.Counter(c for s in subset for c in per_image[s])
        return {
            "clips": len({clip_of(s) for s in subset}),
            "images": len(subset),
            "boxes": sum(per_class.values()),
            "backgrounds": sum(1 for s in subset if not per_image[s]),
            "per_class": {names[i]: per_class.get(i, 0) for i in range(len(names))},
        }

    stats = {name: tally(stems[name]) for name in SPLITS}

    header = "# Generated by prepare_thai.py — do not edit by hand.\n"
    body = (f"path: {out.resolve()}\n"
            "val: images/val\n"
            "test: images/test\n"
            f"names: [{', '.join(names)}]\n")
    (out / "data.yaml").write_text(header + body + "train: images/train\n")

    # Sweep variants: same val/test, a nested prefix of the train clips.
    sweep_order = manifest["sweep_order"]
    sweep = {}
    for pct in FRACTIONS:
        keep = set(sweep_order[:max(1, round(len(sweep_order) * pct / 100))])
        subset = [s for s in stems["train"] if clip_of(s) in keep]
        listing = out / f"train_f{pct}.txt"
        # Absolute paths on purpose. Ultralytics only rewrites lines that start
        # with "./" (substituting the txt file's own directory); anything else
        # is resolved against the CWD, so a relative listing silently finds no
        # images and trains on an empty set. These files are generated per
        # machine and gitignored, so absolute paths cost nothing.
        listing.write_text(
            "".join(f"{(out / 'images' / 'train' / f'{s}.jpg').resolve()}\n" for s in subset)
        )
        (out / f"data_f{pct}.yaml").write_text(header + body + f"train: {listing.name}\n")
        sweep[f"f{pct}"] = tally(subset)
    sweep["f100"] = stats["train"]

    (out / "dataset_meta.json").write_text(json.dumps({
        "label_set": LABEL_SET,
        "names": names,
        "source": str(source),
        "grouped_by": manifest["grouped_by"],
        "seed": manifest["seed"],
        "clips": manifest["clips"],
        "splits": stats,
        "sweep": sweep,
    }, indent=2) + "\n")

    return {"dataset_dir": str(out), "splits": stats, "sweep": sweep}


# --------------------------------------------------------------------------- cli


def _print_table(title: str, rows: dict, names: list[str]) -> None:
    print(f"\n{title}")
    head = f"{'':<8}{'clips':>6}{'imgs':>6}{'bg':>5}" + "".join(f"{n[:6]:>8}" for n in names) + f"{'boxes':>7}"
    print(head)
    print("-" * len(head))
    for key, s in rows.items():
        cells = "".join(f"{s['per_class'][n]:>8}" for n in names)
        print(f"{key:<8}{s['clips']:>6}{s['images']:>6}{s['backgrounds']:>5}{cells}{s['boxes']:>7}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE,
                        help="the CVAT YOLO export (images/train + labels/train)")
    parser.add_argument("--out", type=pathlib.Path, default=HERE / "datasets" / "thai3")
    parser.add_argument("--splits", type=pathlib.Path, default=SPLITS_JSON)
    parser.add_argument("--plan", action="store_true",
                        help="recompute the split and overwrite thai_splits.json")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=40000,
                        help="random clip assignments to try when balancing")
    args = parser.parse_args(argv)

    if not args.source.exists():
        raise SystemExit(f"source not found: {args.source}")

    if args.plan:
        manifest = plan(args.source, args.seed, args.iterations)
        args.splits.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"wrote {args.splits}")
        for name in SPLITS:
            print(f"  {name:<6} {len(manifest['clips'][name]):>2} clips: {manifest['clips'][name]}")
        return 0

    if not args.splits.exists():
        raise SystemExit(f"{args.splits} missing — run with --plan first")
    manifest = json.loads(args.splits.read_text())
    result = build(args.source, args.out, manifest)

    names = classes.label_set(LABEL_SET)[0]
    _print_table("split (grouped by clip — no recording spans two splits)", result["splits"], names)
    _print_table("sweep subsets (nested; val/test identical across all)", result["sweep"], names)
    print(f"\n-> {result['dataset_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
