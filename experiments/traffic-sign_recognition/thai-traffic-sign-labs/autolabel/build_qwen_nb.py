#!/usr/bin/env python3
"""Emit qwen_batch.ipynb. Kept as a script so the notebook stays reviewable as
plain text and diffs like code instead of like a blob of JSON."""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent / "qwen_batch.ipynb"
CELLS = []


def md(t):
    CELLS.append({"cell_type": "markdown", "metadata": {},
                  "source": t.strip("\n").splitlines(True)})


def code(t):
    CELLS.append({"cell_type": "code", "execution_count": None, "metadata": {},
                  "outputs": [], "source": t.strip("\n").splitlines(True)})


md(r"""
# Name the signs in one batch — Qwen2.5-VL

Takes the `crops.zip` that `prelabel.py to-colab` built, and gives back a
`predictions.csv` that `prelabel.py from-colab` reads.

**Before you run anything: Runtime → Change runtime type → T4 GPU.**
On CPU this will appear to work and take about forty times as long.

The whole trip is: upload one zip, run every cell, download one CSV.
""")

md("## 1. Check you actually have a GPU")
code(r"""
import subprocess
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                      "--format=csv,noheader"], capture_output=True, text=True).stdout
      or "NO GPU — Runtime > Change runtime type > T4 GPU, then rerun this cell")
""")

md("""
## 2. Install

A couple of minutes. The pins matter: 4-bit loading needs `bitsandbytes`, and
Qwen2.5-VL needs a `transformers` new enough to know the architecture.
""")
code(r"""
%pip -q install -U "transformers>=4.49" accelerate bitsandbytes qwen-vl-utils
""")

md("""
## 3. Upload `crops.zip`

Run the cell, press **Choose Files**, pick the `crops.zip` out of your batch
folder. `classes.py` and `qwen_label.py` are already inside it — the zip is
self-contained on purpose, so there is no repo to clone and no token to paste.
""")
code(r"""
from google.colab import files
up = files.upload()
name = next(iter(up))
!unzip -qo "{name}" -d /content/batch
!ls /content/batch && echo "crops:" && ls /content/batch/crops | wc -l
""")

md("""
## 4. Name every crop

~1–2 s per crop on a T4, so a 400-crop batch is roughly ten minutes. The first
line of output checks that Qwen is **not** shrinking the crops — if it says
STOP, the run is worthless and the numbers it produces mean nothing.

It appends as it goes, so if Colab drops the session, re-run this cell and it
resumes instead of starting over.
""")
code(r"""
%cd /content/batch
!python qwen_label.py --crops crops --map source_map.csv --out predictions.csv
""")

md("""
## 5. Download the answers

Then, back on your laptop:

```
prelabel.py from-colab <batch> ~/Downloads/predictions.csv
```
""")
code(r"""
import collections, csv
rows = list(csv.DictReader(open("/content/batch/predictions.csv")))
print(len(rows), "crops named\n")
for name, n in collections.Counter(r["pred"] for r in rows).most_common():
    print(f"  {name:26s} {n:4d}")

from google.colab import files
files.download("/content/batch/predictions.csv")
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
