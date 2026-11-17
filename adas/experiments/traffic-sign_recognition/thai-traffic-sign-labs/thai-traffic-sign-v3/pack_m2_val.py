#!/usr/bin/env python3
"""Pack M2's held-out val crops into one .npz, so the DFC machine can score
the quantized model without a copy of the repo or the dataset.

    python pack_m2_val.py       # -> ~/hailo-calib-m2/m2_val_128.npz

uint8 NHWC RGB plus an int label per crop, in the CLASSES order m2.pt uses.
These are the same 1151 crops that gave m2.pt 83.7% and m2.hef 61.9%, and they
are NOT in the calibration set: build_m2_calib.py reads m2/train only.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402

CLASSES = list(classes.THAI_FINE_NAMES) + ["not_a_sign"]
SIZE = 128


def pack(val: Path):
    crops, labels = [], []
    for i, name in enumerate(CLASSES):
        for p in sorted((val / name).glob("*.jpg")):
            im = Image.open(p).convert("RGB")
            if im.size != (SIZE, SIZE):
                im = im.resize((SIZE, SIZE), Image.LANCZOS)
            crops.append(np.asarray(im))
            labels.append(i)
    return np.stack(crops).astype(np.uint8), np.asarray(labels, dtype=np.int16)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--val", default=str(HERE / "m2" / "val"))
    ap.add_argument("--out", default=str(Path.home() / "hailo-calib-m2"))
    args = ap.parse_args()

    x, y = pack(Path(args.val))
    assert len(x) == len(y) and x.shape[1:] == (SIZE, SIZE, 3) and x.dtype == np.uint8
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / f"m2_val_{SIZE}.npz", crops=x, labels=y,
                        classes=np.asarray(CLASSES))
    n = np.bincount(y, minlength=len(CLASSES))
    print(f"{len(x)} crops over {int((n > 0).sum())} classes")
    print(f"-> {out / f'm2_val_{SIZE}.npz'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
