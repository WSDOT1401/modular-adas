#!/usr/bin/env python3
"""Emit notebooks/colab_thai_signs.ipynb. Kept as a script so the notebook is
regenerable and reviewable as plain text."""
import json
import pathlib

OUT = pathlib.Path(
    "/Users/mymacaroni/Documents/GitHub/modular-adas/experiments/"
    "traffic-sign_recognition/notebooks/colab_thai_signs.ipynb"
)

CELLS = []


def md(text):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)})


def code(text):
    CELLS.append({"cell_type": "code", "execution_count": None, "metadata": {},
                  "outputs": [], "source": text.strip("\n").splitlines(True)})


md(r"""
# Thai traffic signs — YOLO26n data-scaling sweep

Trains **4 runs** on nested subsets of the training clips (25 / 50 / 75 / 100 %),
all validated on the **same** held-out split, and plots mAP50 against the number
of training boxes.

**The plot is the deliverable.** The absolute mAP will be low — 291 training
boxes of small, distant signs is a tiny dataset. The argument this notebook
supports is the *slope*: accuracy rises with data, so more annotation is worth
funding.

### Before you run this

1. **Runtime → Change runtime type → GPU** (T4 is enough).
2. **🔑 Secrets** (left sidebar) → add `GITHUB_TOKEN`, a GitHub PAT with `repo`
   scope, and enable notebook access. The repo is private.
3. **Upload the dataset to Drive, once:**
   ```bash
   cd experiments/traffic-sign_recognition/thai-traffic-sign-labs/datasets
   zip -r ~/thai_yolo.zip YOLO          # ~241 MB
   ```
   Put `thai_yolo.zip` in `MyDrive/thai-signs/`. Only `YOLO/` is needed —
   `COCO/images` is a byte-identical duplicate. Re-upload only when labels change.

Expect **40–70 minutes** for the four runs at imgsz 1280.
""")

md("## 1. Configuration")

code(r'''
# ---- EDIT THESE --------------------------------------------------------------
REPO      = "WSDOT1401/modular-adas"
BRANCH    = "experiments/traffic-sign_recognition"
ZIP_PATH  = "/content/drive/MyDrive/thai-signs/thai_yolo.zip"
SECRET    = "GITHUB_TOKEN"          # name of the Colab Secret
# ------------------------------------------------------------------------------

IMGSZ     = 1280     # 49% of boxes are under 16 px at 1024; 1280 halves that.
                     # NOTE: this does NOT run real-time on the Pi CPU — the
                     # existing Pi benchmark measures NCNN at 1024 -> 3.5 FPS.
                     # 1280 is for the accuracy experiment; shipping it depends
                     # on the AI HAT 2 (Hailo), a different export path.
EPOCHS    = 100
BATCH     = 8        # 1280 + 2304x1296 source frames; 16 risks OOM on a T4
FRACTIONS = [25, 50, 75, 100]

WORK      = "/content/work"
DATA      = "/content/data"          # unzipped dataset — local disk, NOT Drive
REPO_DIR  = f"{WORK}/modular-adas"
EXP       = f"{REPO_DIR}/experiments/traffic-sign_recognition"
DATASETS  = f"{WORK}/datasets"
RUNS      = f"{WORK}/runs"

import os
os.makedirs(WORK, exist_ok=True)
print("runs:", [f"f{p}" for p in FRACTIONS], "@ imgsz", IMGSZ)
''')

md(r"""
## 2. Mount Drive and unzip

Unzipped to `/content/data` (local disk), **not** read off the Drive mount —
Drive I/O would bottleneck every epoch.
""")

code(r'''
import pathlib, shutil, subprocess, sys, zipfile
from google.colab import drive

drive.mount("/content/drive")

zip_path = pathlib.Path(ZIP_PATH)
if not zip_path.exists():
    raise SystemExit(
        f"{zip_path} not found.\n"
        "Zip the dataset and put it in Drive — see the header cell:\n"
        "  cd .../thai-traffic-sign-labs/datasets && zip -r ~/thai_yolo.zip YOLO"
    )

if pathlib.Path(DATA).exists():
    shutil.rmtree(DATA)
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(DATA)

# The zip may or may not carry a top-level YOLO/ directory; find it either way.
# Require BOTH images/train and labels/train under the same parent, so a
# half-matching layout fails here with something readable instead of later.
candidates = [d.parent.parent for d in pathlib.Path(DATA).rglob("images/train")
              if d.is_dir() and (d.parent.parent / "labels/train").is_dir()]
if not candidates:
    found = sorted({str(d.relative_to(DATA)) for d in pathlib.Path(DATA).rglob("*") if d.is_dir()})[:15]
    raise SystemExit(
        "no images/train + labels/train pair found under the unzipped dataset.\n"
        f"directories present: {found}\n"
        "Re-zip from the datasets/ dir:  zip -rq ~/thai_yolo.zip YOLO -x '.*' '*/.*'"
    )
source = candidates[0]
n_img = len(list((source / "images/train").glob("*.jpg")))
n_lbl = len(list((source / "labels/train").glob("*.txt")))
print(f"source: {source}\n  {n_img} images, {n_lbl} labels")
assert n_img == n_lbl > 0, f"expected equal nonzero counts, got {n_img} images / {n_lbl} labels"
''')

md(r"""
## 3. Clone the repo

The token goes to `git` through an **argument list**, never `!git clone` — a `!`
magic echoes the whole command, token included, into this notebook's saved
output. Git's own error text also contains the URL, so it is scrubbed before
being raised.
""")

code(r'''
import os

# Pointers only: results/ holds Git-LFS weights this notebook never reads, and a
# full smudge would burn the 1 GB/month LFS bandwidth.
os.environ["GIT_LFS_SKIP_SMUDGE"] = "1"

from google.colab import userdata
token = userdata.get(SECRET)

if pathlib.Path(REPO_DIR).exists():
    shutil.rmtree(REPO_DIR)

url = f"https://x-access-token:{token}@github.com/{REPO}.git"
try:
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", BRANCH, url, REPO_DIR],
        check=True, capture_output=True, text=True,
    )
except subprocess.CalledProcessError as exc:
    raise SystemExit("clone failed: " + (exc.stderr or "").replace(token, "***")) from None
finally:
    del token, url

sys.path.insert(0, EXP)
print("cloned", REPO, "@", BRANCH)
''')

md("## 4. Install dependencies")

code(r'''
!pip install -q "ultralytics>=8.4.69"
import ultralytics
print("ultralytics", ultralytics.__version__)
''')

md(r"""
## 5. Build the split

**Grouped by clip.** The 330 frames are 30 dashcam recordings sliced up; frames
from one recording share roads, lighting and often the same physical sign. A
random per-image split would validate on roads the model already memorised,
inflating the low-data end of the curve and flattening the very slope we are
trying to show.

The split itself is fixed in the committed `thai_splits.json`, so it is
identical on every machine and every rerun.
""")

code(r'''
subprocess.run(
    [sys.executable, f"{EXP}/prepare_thai.py", "--source", str(source), "--out", f"{DATASETS}/thai3"],
    check=True,
)

import json
meta = json.loads(pathlib.Path(f"{DATASETS}/thai3/dataset_meta.json").read_text())

# Belt and braces: prepare_thai.py already refuses a leaking split, but this is
# the claim the whole experiment rests on, so assert it here too.
seen = {}
for split, clips in meta["clips"].items():
    for c in clips:
        assert c not in seen, f"clip {c} in both {seen[c]} and {split}"
        seen[c] = split
print(f"{len(seen)} clips, no clip spans two splits ✓")
''')

md(r"""
## 6. Train the sweep

Four runs, sequential. Each fraction gets its own `project` directory, which is
what keeps the run folders apart — `train.py` derives the run name from
`label_set` and `imgsz` only, which are identical across the sweep.

A failing run is logged and skipped rather than killing the rest, so one bad
export does not cost you the other three results.
""")

code(r'''
import time, traceback
import train

results = {}
for pct in FRACTIONS:
    yaml = f"{DATASETS}/thai3/" + ("data.yaml" if pct == 100 else f"data_f{pct}.yaml")
    print(f"\n{'=' * 70}\nf{pct}  ({meta['sweep'][f'f{pct}']['boxes']} train boxes)\n{'=' * 70}")
    started = time.perf_counter()
    try:
        results[pct] = train.train_one(
            pathlib.Path(yaml), "thai3", IMGSZ,
            epochs=EPOCHS, project=pathlib.Path(f"{RUNS}/f{pct}"),
            batch=BATCH,
            cache=False,      # 2304x1296 frames: caching 221 of them would OOM Colab
            export=(pct == 100),   # only the full model needs NCNN artifacts
        )
    except Exception as exc:
        print(f"f{pct} FAILED after {time.perf_counter() - started:.0f}s: {exc!r}")
        traceback.print_exc()
        results[pct] = {"error": repr(exc)}

ok = [p for p, r in results.items() if "error" not in r]
print(f"\n{len(ok)}/{len(FRACTIONS)} runs succeeded: {ok}")
''')

md(r"""
## 7. The curve

`mAP50` is the headline. `mAP50-95` will look weak partly because the sign-border
convention in the annotations is not fully consistent (boxes sometimes include
the backing plate, sometimes clip into the sign face) — that noise is constant
across all four points, so it shifts the whole curve down without changing its
shape.
""")

code(r'''
import matplotlib.pyplot as plt

rows = []
for pct in FRACTIONS:
    r = results.get(pct, {})
    if "error" in r or not r:
        continue
    m = r["metrics"]
    rows.append({
        "pct": pct,
        "clips": meta["sweep"][f"f{pct}"]["clips"],
        "images": meta["sweep"][f"f{pct}"]["images"],
        "boxes": meta["sweep"][f"f{pct}"]["boxes"],
        "mAP50": m["metrics/mAP50(B)"],
        "mAP50-95": m["metrics/mAP50-95(B)"],
        "P": m["metrics/precision(B)"],
        "R": m["metrics/recall(B)"],
        "min": r["wall_seconds"] / 60,
    })

hdr = f"{'data':>6}{'clips':>7}{'imgs':>6}{'boxes':>7}{'mAP50':>9}{'mAP50-95':>10}{'P':>8}{'R':>8}{'min':>7}"
print(hdr); print("-" * len(hdr))
for r in rows:
    print(f"{str(r['pct']) + '%':>6}{r['clips']:>7}{r['images']:>6}{r['boxes']:>7}"
          f"{r['mAP50']:>9.4f}{r['mAP50-95']:>10.4f}{r['P']:>8.3f}{r['R']:>8.3f}{r['min']:>7.1f}")

if rows:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot([r["boxes"] for r in rows], [r["mAP50"] for r in rows], "o-", label="mAP50")
    ax.plot([r["boxes"] for r in rows], [r["mAP50-95"] for r in rows], "s--", label="mAP50-95")
    for r in rows:
        ax.annotate(f"{r['pct']}%", (r["boxes"], r["mAP50"]),
                    textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9)
    ax.set_xlabel("training boxes")
    ax.set_ylabel("mAP (held-out val, grouped by clip)")
    ax.set_title(f"YOLO26n @ {IMGSZ} — Thai traffic signs, 3 classes")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(f"{RUNS}/scaling_curve.png", dpi=150)
    plt.show()
''')

md(r"""
## 8. Test set — evaluated once

The sweep above is validated on `val`, which early stopping also watches. `test`
is four recordings that nothing in training or model selection has seen, and it
is scored **once**, for the 100 % model only. Do not iterate against this number.
""")

code(r'''
from ultralytics import YOLO

if 100 in results and "error" not in results[100]:
    best = results[100]["best_pt"]
    m = YOLO(best).val(
        data=f"{DATASETS}/thai3/data.yaml", imgsz=IMGSZ, split="test",
        project=f"{RUNS}/f100", name="val_test", exist_ok=True, plots=True,
    )
    d = m.results_dict
    print(f"\nTEST  mAP50={d['metrics/mAP50(B)']:.4f}  mAP50-95={d['metrics/mAP50-95(B)']:.4f}  "
          f"P={d['metrics/precision(B)']:.3f}  R={d['metrics/recall(B)']:.3f}")
    print(f"      ({meta['splits']['test']['boxes']} boxes across "
          f"{meta['splits']['test']['clips']} unseen recordings)")
    # class_result(i) indexes ap_class_index order, NOT class id — a class with
    # no test instances is omitted and every later index shifts.
    print("\nper class:")
    seen = {int(c): i for i, c in enumerate(m.box.ap_class_index)}
    for cid, name in enumerate(meta["names"]):
        if cid not in seen:
            print(f"  {name:<14} (no instances in test)")
            continue
        p, r, ap50, ap = m.box.class_result(seen[cid])
        print(f"  {name:<14} P={p:.3f} R={r:.3f} mAP50={ap50:.4f} mAP50-95={ap:.4f}")
else:
    print("the 100% run did not finish — nothing to evaluate")
''')

md(r"""
## 9. Save results back to Drive

Weights, plots, `run_meta.json` and the curve. Colab wipes `/content` when the
session ends, so this cell is what makes the work survive.
""")

code(r'''
dest = pathlib.Path("/content/drive/MyDrive/thai-signs")
dest.mkdir(parents=True, exist_ok=True)
stamp = time.strftime("%Y%m%d-%H%M")
archive = shutil.make_archive(str(dest / f"thai_runs_{stamp}"), "zip", RUNS)
print("saved", archive, f"({pathlib.Path(archive).stat().st_size / 1e6:.0f} MB)")
print("\nalso committed to the repo for the record:")
print("  experiments/traffic-sign_recognition/thai_splits.json  (the split)")
''')

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "accelerator": "GPU",
        "colab": {"provenance": [], "gpuType": "T4"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}, indent=1) + "\n")
print("wrote", OUT, f"({len(CELLS)} cells)")
