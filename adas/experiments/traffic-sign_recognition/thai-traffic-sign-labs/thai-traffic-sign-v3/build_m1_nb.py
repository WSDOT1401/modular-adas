#!/usr/bin/env python3
"""Emit m1_batch.ipynb. Same deal as autolabel/build_train_nb.py -- the
notebook stays reviewable as plain text and diffs like code, not like JSON."""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "m1_batch.ipynb"
FLOORS = [0, 16, 24]
CELLS = []


def md(t):
    CELLS.append({"cell_type": "markdown", "metadata": {},
                  "source": t.strip("\n").splitlines(True)})


def code(t):
    CELLS.append({"cell_type": "code", "execution_count": None, "metadata": {},
                  "outputs": [], "source": t.strip("\n").splitlines(True)})


md(r"""
# M1 — how small a sign should we train on?

M1 only has to find *where* a sign is, not which one. One class, `sign`.

A sign enters frame far away and grows as you drive at it. We do **not** need
the far-away frames — M1 catching it once it is clearly a sign is enough,
because M2 cannot read a 12 px crop anyway. So the question is not "how low
can the floor go" but "where do we cut so M1 stops firing on horizon smudges".

Three runs, identical except for the training-label floor:

| run | floor @1280 | = source px | train boxes |
|-----|-------------|-------------|-------------|
| `floor00` | none | — | 982 |
| `floor16` | 16 px | 29 px | 627 |
| `floor24` | 24 px | 43 px | 377 |

All three are scored on the **same** 163 val boxes (>= 24 source px — the
smallest crop M2 can read). Letting each run keep its own filtered val set
would make a high floor look good for free: you deleted the hard questions.

**Before anything else: Runtime → Change runtime type → T4 GPU.**
Budget roughly 2 h for all three.
""")

md("## 1. GPU")
code(r"""
import subprocess
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                      "--format=csv,noheader"], capture_output=True, text=True).stdout
      or "NO GPU — Runtime > Change runtime type > T4 GPU, then rerun this cell")
""")

md("## 2. Install")
code(r"""
%pip -q install -U ultralytics
""")

md(r"""
## 3. Dataset

Reuses the **b01.zip already in your Drive** — the variants are built on Colab,
so there is nothing new to upload. Images are symlinked into each variant, so
three copies cost no disk.
""")
code(r"""
from google.colab import drive
drive.mount("/content/drive")

ZIP = "/content/drive/MyDrive/b01.zip"      # <- change if you named it differently
!unzip -q -o "$ZIP" -d /content
""")

code("%%writefile /content/build_m1.py\n" + (HERE / "build_m1.py").read_text())

code(r"""
!python /content/build_m1.py --src /content/dataset --out /content/m1 --floors 0 16 24
""")

md(r"""
## 4. Look at the boxes before spending two hours on them

Coordinates go pixels → normalised → CVAT → normalised → pixels on the way
here, and when that breaks it breaks *silently*: training finishes and hands
you a plausible-looking bad number.

The picture is the real check. Green boxes not on signs → stop.

The second thing to read is the drop count. `floor24` should show far fewer
train boxes than `floor00` and **exactly the same** val boxes.
""")
code(r"""
import pathlib, random
import matplotlib.pyplot as plt, matplotlib.patches as mpatches
from PIL import Image

FLOORS = ["floor00", "floor16", "floor24"]
print(f"{'variant':10s}{'train':>8}{'val':>6}{'bg frames':>11}")
for v in FLOORS:
    d = pathlib.Path("/content/m1") / v
    n = {}
    bg = 0
    for s in ("train", "val"):
        rows = [len([r for r in p.read_text().splitlines() if r.strip()])
                for p in (d / "labels" / s).glob("*.txt")]
        n[s] = sum(rows)
        bg += sum(1 for r in rows if r == 0)
    print(f"{v:10s}{n['train']:>8}{n['val']:>6}{bg:>11}")

d = pathlib.Path("/content/m1/floor16")
cand = [p for p in (d / "labels/train").glob("*.txt") if p.read_text().strip()]
p = d / "images/train" / f"{random.choice(sorted(cand)).stem}.jpg"
im = Image.open(p); W, H = im.size
fig, ax = plt.subplots(figsize=(13, 8)); ax.imshow(im); ax.axis("off"); ax.set_title(p.name)
for c, x, y, w, h in (r.split() for r in
                      (d / "labels/train" / f"{p.stem}.txt").read_text().splitlines() if r.strip()):
    x, y, w, h = (float(v) for v in (x, y, w, h))
    ax.add_patch(mpatches.Rectangle(((x - w / 2) * W, (y - h / 2) * H), w * W, h * H,
                                    fill=False, lw=2, color="lime"))
plt.show()
""")

md(r"""
## 5. Train all three

The recipe is b01's, unchanged, so the only thing that moved is the floor:
`imgsz=1280` (a sign is 30–60 px and at 640 most are gone before the first
convolution), `AdamW`/`lr0=0.001` and `mosaic=0.5` because the set is under
1000 images, `epochs=50` as a *schedule* not a budget — the LR decays across
whatever you declare, so stopping early means it never came down.

`fliplr=0.0` is kept for the same reason b01 had it, even though the reason has
expired: a mirrored `turn_left` was a `turn_right`, and with one class that no
longer matters. Mirroring is free data for M1 now — but turning it on here
would move two things at once. Test it after the floor is settled.

Re-running this cell after a dropped session carries on from `last.pt`.
""")
code(r"""
import pathlib
import torch
from ultralytics import YOLO

PROJECT = "/content/drive/MyDrive/thai-traffic-sign-dataset/v1/results"
FLOORS = ["floor00", "floor16", "floor24"]

for v in FLOORS:
    name = f"m1-{v}"
    last = pathlib.Path(PROJECT) / name / "weights/last.pt"
    # Resume only a run that was actually cut off. A finished run leaves last.pt
    # with epoch == -1, and resume=True on that raises "nothing to resume".
    unfinished = last.exists() and torch.load(
        last, map_location="cpu", weights_only=False).get("epoch", -1) >= 0
    if last.exists() and not unfinished:
        print(f"{name}: already finished, skipping")
        continue

    print(f"\n=== {name} ===")
    YOLO(str(last) if unfinished else "yolo26n.pt").train(
        data=f"/content/m1/{v}/data.yaml",
        imgsz=1280,
        epochs=50,
        patience=20,
        batch=8,
        optimizer="AdamW", lr0=0.001,
        mosaic=0.5, mixup=0.0, copy_paste=0.0,
        fliplr=0.0,
        seed=0,
        project=PROJECT, name=name, exist_ok=True,
        resume=unfinished,
        plots=True,
    )
""")

md(r"""
## 6. Compare

Every run is scored on the same val labels, so these three rows are directly
comparable. Recall is the one that answers the question: of the signs M2 could
actually have read, how many did M1 hand it?

**163 val boxes means one missed sign moves recall by 0.6%.** A 1–2% gap
between runs is three signs and could flip on a different split. Do not crown a
winner under about 3%.

Watch precision too — the whole point of a floor is that it should *rise* as
the horizon smudges leave the training set.
""")
code(r"""
from ultralytics import YOLO

print(f"{'run':14s}{'P':>8}{'R':>8}{'mAP50':>8}{'mAP50-95':>10}")
for v in FLOORS:
    m = YOLO(f"{PROJECT}/m1-{v}/weights/best.pt").val(
        data="/content/m1/floor00/data.yaml", imgsz=1280, verbose=False)
    b = m.box
    print(f"{v:14s}{b.mp:>8.3f}{b.mr:>8.3f}{b.map50:>8.3f}{b.map:>10.3f}")
""")

md(r"""
## 7. Take the winner home

Also lands in your Drive under `results/m1-<variant>/weights/`.
""")
code(r"""
WINNER = "floor16"          # <- set this after reading the table
from google.colab import files
files.download(f"{PROJECT}/m1-{WINNER}/weights/best.pt")
""")

OUT.write_text(json.dumps({
    "cells": CELLS,
    "metadata": {"accelerator": "GPU",
                 "colab": {"provenance": [], "gpuType": "T4"},
                 "kernelspec": {"display_name": "Python 3", "name": "python3"},
                 "language_info": {"name": "python"}},
    "nbformat": 4, "nbformat_minor": 0,
}, indent=1) + "\n")
print(f"wrote {OUT} ({len(CELLS)} cells)")
