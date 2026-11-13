#!/usr/bin/env python3
"""Build the M1 dataset variants.

M1 is class-agnostic: every box becomes class 0 `sign`.

The variants differ in ONE thing -- the training-label size floor, measured in
pixels at the network input (imgsz 1280). Boxes under the floor are deleted
from the label file but their frame stays, so the model learns that a horizon
smudge is background.

Val labels are IDENTICAL in every variant, fixed at >= 24 source px (the
smallest crop M2 can read). Scoring each run against its own filtered val set
would make a high floor look good for free.

Images are symlinked, so a variant costs no disk. Runs the same on Colab.
"""
import argparse
import os
from pathlib import Path

from PIL import Image

VAL_FLOOR_SRC = 24   # source px -- M2's minimum usable crop
IMGSZ = 1280         # train floors are measured at this network input


def build(src, dst, floor_net):
    for split in ("train", "val"):
        (dst / "images" / split).mkdir(parents=True, exist_ok=True)
        (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
        kept = dropped = 0
        for img in sorted((src / "images" / split).glob("*.jpg")):
            link = dst / "images" / split / img.name
            if not link.is_symlink():
                os.symlink(img.resolve(), link)
            lab = src / "labels" / split / f"{img.stem}.txt"
            W, H = Image.open(img).size
            out = []
            for line in (lab.read_text().splitlines() if lab.exists() else []):
                p = line.split()
                if len(p) < 5:
                    continue
                short = min(float(p[3]) * W, float(p[4]) * H)
                ok = (short >= VAL_FLOOR_SRC if split == "val"
                      else short * IMGSZ / max(W, H) >= floor_net)
                if ok:
                    out.append("0 " + " ".join(p[1:5]))
                    kept += 1
                else:
                    dropped += 1
            (dst / "labels" / split / f"{img.stem}.txt").write_text(
                "\n".join(out) + ("\n" if out else ""))
        print(f"  {split:5s} {kept:4d} boxes kept, {dropped:4d} dropped")
    (dst / "data.yaml").write_text(
        f"path: {dst.resolve()}\ntrain: images/train\nval: images/val\n"
        f"nc: 1\nnames: ['sign']\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../autolabel/dataset")
    ap.add_argument("--out", default="m1")
    ap.add_argument("--floors", type=int, nargs="+", default=[0, 16, 24])
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)

    for f in a.floors:
        print(f"floor {f:2d} px @{IMGSZ}  (>= {f * 2304 / IMGSZ:.0f} source px)")
        build(src, out / f"floor{f:02d}", f)

    ref = None
    for f in a.floors:
        got = {p.name: p.read_text()
               for p in (out / f"floor{f:02d}" / "labels/val").glob("*.txt")}
        assert ref is None or got == ref, f"floor{f:02d} val labels differ from the others"
        ref = got
    print("ok: val labels identical across all variants")


if __name__ == "__main__":
    main()
