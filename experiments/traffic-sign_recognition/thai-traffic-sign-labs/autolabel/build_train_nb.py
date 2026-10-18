#!/usr/bin/env python3
"""Emit train_batch.ipynb. Same deal as build_qwen_nb.py -- the notebook stays
reviewable as plain text and diffs like code instead of like a blob of JSON."""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent / "train_batch.ipynb"
CELLS = []


def md(t):
    CELLS.append({"cell_type": "markdown", "metadata": {},
                  "source": t.strip("\n").splitlines(True)})


def code(t):
    CELLS.append({"cell_type": "code", "execution_count": None, "metadata": {},
                  "outputs": [], "source": t.strip("\n").splitlines(True)})


md(r"""
# Train the detector on your batches

Takes the `dataset/` that `prelabel.py build` wrote, and gives back a `best.pt`.

**Before anything else: Runtime → Change runtime type → T4 GPU.**

Everything is written straight to your Drive, so a dropped Colab session costs
you nothing — re-run the training cell and it carries on from the last epoch.
""")

md("## 1. Check you actually have a GPU")
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
## 3. Bring the dataset in

On your laptop:

```
cd autolabel && zip -qr b01.zip dataset
```

Upload that zip to the top of your Drive (`MyDrive`), then run this cell. The
`sed` matters: `data.yaml` holds the absolute path of the Mac that built it, and
on Colab that directory does not exist.
""")
code(r"""
from google.colab import drive
drive.mount("/content/drive")

ZIP = "/content/drive/MyDrive/b01.zip"      # <- change if you named it differently
!unzip -q -o "$ZIP" -d /content
!sed -i 's|^path:.*|path: /content/dataset|' /content/dataset/data.yaml
!cat /content/dataset/data.yaml
""")

md(r"""
## 4. Check the labels before spending two hours on them

Box coordinates go pixels → normalised → CVAT → normalised → pixels on the way
here, and when that breaks it breaks *silently*: training runs to completion and
produces a plausible-looking bad number. Thirty seconds now, or two hours later.

The picture is the real check. If the green boxes are not on the signs, stop.
""")
code(r"""
import collections, pathlib, random, yaml
import matplotlib.pyplot as plt, matplotlib.patches as mpatches
from PIL import Image

D = pathlib.Path("/content/dataset")
NAMES = yaml.safe_load((D / "data.yaml").read_text())["names"]

bad, count, stems, with_boxes = [], {}, {}, []
for s in ("train", "val"):
    imgs = {p.stem for p in (D / "images" / s).glob("*.jpg")}
    labs = {p.stem for p in (D / "labels" / s).glob("*.txt")}
    stems[s] = imgs
    if imgs - labs:
        bad.append(f"{s}: {len(imgs-labs)} images have no label file")
    if labs - imgs:
        bad.append(f"{s}: {len(labs-imgs)} label files have no image")
    count[s] = collections.Counter()
    for p in (D / "labels" / s).glob("*.txt"):
        rows = [r.split() for r in p.read_text().splitlines() if r.strip()]
        if rows and s == "train":
            with_boxes.append(p.stem)
        for c, *xywh in rows:
            count[s][int(c)] += 1
            if not 0 <= int(c) < len(NAMES):
                bad.append(f"{p.name}: class {c} is not one of the {len(NAMES)} names")
            if not all(0 <= float(v) <= 1 for v in xywh):
                bad.append(f"{p.name}: a coordinate is outside 0..1")

# Split by clip, not by frame: frames 2 s apart hold the same physical sign, so
# the same frame_id on both sides -- or two frames of one clip -- inflates val.
leak = stems["train"] & stems["val"]
if leak:
    bad.append(f"{len(leak)} frames are in BOTH train and val")
clips = {s: {x.rsplit("_f", 1)[0] for x in stems[s]} for s in stems}
shared = clips["train"] & clips["val"]
if shared:
    bad.append(f"{len(shared)} clips appear in both splits: {sorted(shared)[:3]}")

n_bg = sum(1 for s in ("train", "val")
           for p in (D / "labels" / s).glob("*.txt") if not p.read_text().strip())
print(f"{len(stems['train'])} train / {len(stems['val'])} val images, "
      f"{n_bg} of them sign-free\n")
print(f"{'class':24s}{'train':>7}{'val':>6}")
for i, n in enumerate(NAMES):
    flag = "  <- nothing to learn from" if count["train"][i] < 5 else ""
    print(f"{n:24s}{count['train'][i]:>7}{count['val'][i]:>6}{flag}")
print("\n" + ("\n".join(bad) if bad else "no problems found"))

p = D / "images/train" / f"{random.choice(sorted(with_boxes))}.jpg"
im = Image.open(p); W, H = im.size
fig, ax = plt.subplots(figsize=(13, 8)); ax.imshow(im); ax.axis("off"); ax.set_title(p.name)
for c, x, y, w, h in (r.split() for r in
                      (D / "labels/train" / f"{p.stem}.txt").read_text().splitlines() if r.strip()):
    x, y, w, h = (float(v) for v in (x, y, w, h))
    ax.add_patch(mpatches.Rectangle(((x - w / 2) * W, (y - h / 2) * H), w * W, h * H,
                                    fill=False, lw=2, color="lime"))
    ax.text((x - w / 2) * W, (y - h / 2) * H - 8, NAMES[int(c)], color="lime", fontsize=10)
plt.show()
""")

md(r"""
## 5. Train

About 1.5–2 hours for 100 epochs on a T4, though `patience=20` usually stops it
earlier. Re-running this cell after a disconnect resumes from `last.pt`.

Two settings are not defaults and both matter:

- **`fliplr=0.0`** — the default is 0.5, which mirrors half your images.
  A mirrored `turn_left` *is* a `turn_right`, and a mirrored `keep_left` is a
  `keep_right`. Leave it on and you teach the model that those classes are the
  same thing while the label insists they are not.
- **`imgsz=1280`** — your frames are 2304×1296 and a sign is 30–60 px. At the
  default 640 most of them are gone before the first convolution.

`yolo11n` is the Pi-sized model. Swap in `yolo11s.pt` if you want a better
number and do not mind roughly double the time — the dataset is the limit here,
not the architecture.
""")
code(r"""
import pathlib
from ultralytics import YOLO

PROJECT, NAME = "/content/drive/MyDrive/sign_runs", "b01"
last = pathlib.Path(PROJECT) / NAME / "weights/last.pt"

model = YOLO(str(last)) if last.exists() else YOLO("yolo11n.pt")
model.train(
    data="/content/dataset/data.yaml",
    imgsz=1280,
    epochs=100,
    patience=20,
    batch=8,
    fliplr=0.0,
    seed=0,
    project=PROJECT, name=NAME, exist_ok=True,
    resume=last.exists(),
    plots=True,
)
""")

md(r"""
## 6. Read the per-class table, not the average

`val` prints one row per class. Read those rows.

The `all` row averages every class equally, so six classes with two boxes each
drag it down and tell you nothing about the model you actually have. A class
with fewer than ~10 val instances has an mAP that is noise — one missed box
moves it by ten points.

What you are looking for: the classes with real support (`information`,
`other_warning`, `pedestrian_crossing`, `no_stopping_parking`) should be
climbing batch over batch. The starving ones are a filming problem, not a
training problem.
""")
code(r"""
from ultralytics import YOLO
YOLO(f"{PROJECT}/{NAME}/weights/best.pt").val(
    data="/content/dataset/data.yaml", imgsz=1280, plots=True)
""")

md(r"""
## 7. Take the weights home

They are already in your Drive at `sign_runs/b01/weights/best.pt` — this just
also drops a copy in your browser.

Then point the pipeline at them, and the next batch arrives pre-annotated by a
model that has seen this one:

```
# prelabel.py, near the top
MODEL = HERE / "weights/b01-best.pt"
```

Re-run **score** in the web app so the contact sheet badges come from the new
model too. `batch.json` records which weights scored each batch, because an
accept rate means nothing without knowing what produced it.
""")
code(r"""
from google.colab import files
files.download(f"{PROJECT}/{NAME}/weights/best.pt")
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
