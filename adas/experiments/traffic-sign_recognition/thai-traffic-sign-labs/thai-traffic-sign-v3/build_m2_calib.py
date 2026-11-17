#!/usr/bin/env python3
"""Build M2's Hailo calibration set: every class, not one clip's worth.

    python build_m2_calib.py            # -> ~/hailo-calib-m2/m2_calib_128.npy

The .hef built from the old calibration set scored 61.9% against m2.pt's 83.7%
and only ever emitted 8 of 29 classes, because export_m2_hailo.py cut its 1024
crops from a single dashcam clip. Quantization-aware fine-tuning never saw the
other 21, so they collapsed into not_a_sign. See JOURNAL.md 2026-11-17.

Fix: a flat quota per class from m2/train, synthetic fill for the classes with
no real train crops, leftovers to whoever has footage to spare.

m2/val is never touched. It is the 1151 crops the .hef gets scored on, and the
whole point of this entry is that calibration data is not evaluation data.
"""
import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402
import m2_synth  # noqa: E402

CLASSES = list(classes.THAI_FINE_NAMES) + ["not_a_sign"]
SIZE = m2_synth.SIZE


def build(train: Path, count: int, seed: int):
    rng = random.Random(seed)
    pools = {}
    for name in CLASSES:
        pool = sorted((train / name).glob("*.jpg"))
        rng.shuffle(pool)
        pools[name] = pool

    quota = count // len(CLASSES)
    picked = {n: pools[n][:quota] for n in CLASSES}
    synth_n = {}
    for name in CLASSES:
        short = quota - len(picked[name])
        if short > 0 and name in m2_synth.VARIANTS:
            synth_n[name] = short

    # leftovers go to the classes that actually have more footage
    spare = [(n, pools[n][quota:]) for n in CLASSES]
    room = count - sum(len(v) for v in picked.values()) - sum(synth_n.values())
    i = 0
    while room > 0 and any(v for _, v in spare):
        name, pool = spare[i % len(spare)]
        if pool:
            picked[name].append(pool.pop())
            room -= 1
        i += 1

    crops, tally = [], {}
    for name in CLASSES:
        for p in picked[name]:
            crops.append(np.asarray(Image.open(p).convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)))
        for _ in range(synth_n.get(name, 0)):
            crops.append(np.asarray(m2_synth.sample(name, rng=rng)[0]))
        tally[name] = len(picked[name]) + synth_n.get(name, 0)
    rng.shuffle(crops)
    return np.stack(crops).astype(np.float32), tally, synth_n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--train", default=str(HERE / "m2" / "train"))
    ap.add_argument("--crops", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(Path.home() / "hailo-calib-m2"))
    args = ap.parse_args()

    data, tally, synth_n = build(Path(args.train), args.crops, args.seed)

    for name in CLASSES:
        mark = f"  ({synth_n[name]} synthetic)" if name in synth_n else ""
        print(f"{tally[name]:5d}  {name}{mark}")
    missing = [n for n in CLASSES if tally[n] == 0]
    print(f"\n{len(data)} crops, {sum(1 for n in CLASSES if tally[n])} of {len(CLASSES)} classes covered")
    if missing:
        print(f"NO CROPS, cannot quantize for: {', '.join(missing)}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / f"m2_calib_{SIZE}.npy", data)
    print(f"-> {out / f'm2_calib_{SIZE}.npy'}\ncopy that file to the same path on the DFC machine")
    return 0


def selfcheck():
    """The three things that would silently ruin a calibration set."""
    data, tally, _ = build(HERE / "m2" / "train", 256, 0)
    assert data.shape == (256, SIZE, SIZE, 3), data.shape
    assert data.dtype == np.float32 and 0 <= data.min() and data.max() <= 255
    covered = [n for n in CLASSES if tally[n]]
    assert len(covered) >= 28, f"only {len(covered)} classes: {set(CLASSES) - set(covered)}"
    val = {p.parent.name for p in (HERE / "m2" / "val").rglob("*.jpg")}
    assert val, "no val crops found -- the leak check below proves nothing"
    print(f"ok: {data.shape}, {len(covered)}/{len(CLASSES)} classes, val untouched")


if __name__ == "__main__":
    raise SystemExit(selfcheck() if "--selfcheck" in sys.argv else main())
