#!/usr/bin/env python3
"""Every crop of one class on one sheet, so you can look at them.

    python sheet.py reserved_for_bus    # -> sheet/reserved_for_bus.png
    python sheet.py                     # every class with crops

Reads the current m2/ dataset, so it shows what M2 is actually being trained
and scored on -- not what reviewed.csv says, which is a step upstream.

Every label problem this project has caught was caught this way: the wrong
turn-sign artwork, the `no_left_turn` crops that were really no-parking, and
19 bus-stop boards sitting in a class called `reserved_for_bus`. Not by any
filter, by rendering a class and looking at it.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
M2 = HERE / "m2"
S, COLS, PAD = 128, 10, 14


def crops(name):
    """train first, then val, so a split oddity is visible as a block."""
    return [(s, p) for s in ("train", "val")
            for p in sorted((M2 / s / name).glob("*.jpg"))]


def sheet(name, out):
    got = crops(name)
    if not got:
        return 0
    rows = (len(got) + COLS - 1) // COLS
    img = Image.new("RGB", (COLS * (S + 4) + 8, rows * (S + PAD + 4) + 8), "white")
    d = ImageDraw.Draw(img)
    for k, (split, p) in enumerate(got):
        x, y = 8 + (k % COLS) * (S + 4), 8 + (k // COLS) * (S + PAD + 4)
        img.paste(Image.open(p).resize((S, S)), (x, y))
        d.text((x + 2, y + S + 2), f"{split} {p.stem}"[:24],
               fill="black" if split == "train" else "#b00")
    out.parent.mkdir(exist_ok=True)
    img.save(out)
    return len(got)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", nargs="?", help="a class name; omit for all of them")
    a = ap.parse_args()

    have = sorted({p.name for s in ("train", "val") for p in (M2 / s).iterdir()
                   if p.is_dir()})
    if not have:
        sys.exit(f"no crops under {M2} — run build_m2.py first")
    if a.name and a.name not in have:
        sys.exit(f"no class {a.name!r}. have: {', '.join(have)}")

    for name in [a.name] if a.name else have:
        out = HERE / "sheet" / f"{name}.png"
        n = sheet(name, out)
        if n:
            print(f"{n:4d}  {out}")


if __name__ == "__main__":
    main()
