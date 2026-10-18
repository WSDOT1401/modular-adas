# autolabel — a human-in-the-loop pipeline for building a traffic-sign dataset

Dashcam footage in, a YOLO detection dataset out, with a human reviewing every
single frame. Built for Thai signs on a Raspberry Pi, but nothing here is Thai
except one file — see **Porting this to your country**.

The point is not to remove the human. It is to make sure that by the time a
human looks at a frame, the boxes are already drawn and already named, so the
job is *checking* rather than *drawing*.

## Where the humans are

```
    footage
       │
   [ HUMAN ]  pick the frames worth labelling, on a contact sheet
       │      the detector has already badged each one "sign" / "empty"
       ▼
     batch ──► detector ──► crops ──► Qwen2.5-VL names each sign
       │                                        │
       ▼                                        ▼
   [ HUMAN ]  review every frame in CVAT, boxes pre-drawn and pre-named
       │
       ▼
   YOLO dataset
```

Two human steps, two tools. The first decides *what gets labelled*; the second
decides *whether the labels are right*. Everything between them is a machine
making a first draft that a human is expected to correct.

## What you need

- Python 3.11+ with `flask`, `opencv-python`, `ultralytics`, `pillow`
- A trained sign detector (`.pt`). Three coarse classes is plenty to start —
  it only has to find signs, not name them.
- A free Google Colab account with a T4, for the naming step
- [CVAT](https://github.com/cvat-ai/cvat), self-hosted with Docker, for review

```bash
conda activate <your-env>
pip install flask opencv-python ultralytics pillow
```

## The steps

### 1. Drop footage in and pick frames

```bash
cd app && python app.py        # http://127.0.0.1:5001
```

Put videos in `app/footage/`, then for each clip press **extract** (cuts stills
every 2 s) and **score** (runs the detector, ~0.5 s a frame).

Open a clip. Every thumbnail carries a badge: how many signs the detector found.
`2` means two, `–` means none. The toolbar filters to **has sign** or **empty**,
and counts as you go:

```
picked 103 — 62 sign / 41 empty (40% empty ✓)
```

Click a frame to pick it, shift-click for a range. **Click the badge when the
detector is wrong** — that records your disagreement rather than overwriting the
detector's opinion, so you can measure later how often it missed.

Aim for around 40% sign-free frames. Frames with no signs are real training
data: they teach the model what *isn't* a sign, which is most of what a camera
on a road actually sees.

Back on the homepage, tick the clips you picked from, type a batch id, press
**Create batch**.

### 2. Name the signs

```bash
python prelabel.py detect    b01      # cuts one crop per box
python prelabel.py to-colab  b01      # -> batches/b01-<date>/crops.zip
```

Upload `crops.zip` to Colab, open `qwen_batch.ipynb`, run every cell, download
`predictions.csv`. The zip is self-contained — no repo to clone, no token.

```bash
python prelabel.py from-colab b01 ~/Downloads/predictions.csv
```

### 3. Review in CVAT

```bash
python prelabel.py to-cvat b01        # -> batches/b01-<date>/review.zip
```

In CVAT: create a task whose labels are **exactly `obj.names`, in that order**
(the order is load-bearing — YOLO stores class *indices*, so a reordered list
silently relabels every box). Upload `review.zip` as the task data, then
**Actions → Upload annotations → YOLO 1.1 →** the same zip.

Your group now sees every frame with its boxes already drawn and named. They
fix labels, nudge boxes, delete what isn't a sign, draw what was missed. Empty
frames appear too — confirming emptiness is how a missed sign gets caught.

When they finish: **Actions → Export task dataset → YOLO 1.1**, untick *Save
images*.

```bash
python prelabel.py from-cvat b01 ~/Downloads/task_export.zip
```

This prints the number that matters:

```
What the review cost, against 312 boxes we proposed:
    241 accepted as-is      (77%)
     38 kept, relabelled
     33 deleted (not a sign)
     19 drawn by hand (signs the detector missed)
```

The accept rate is the real measure of whether pre-annotation is saving anybody
any work. Offline accuracy on crops nobody had to fix is not.

### 4. Build the dataset

```bash
python prelabel.py build              # every reviewed batch -> dataset/
```

Lost track of where a batch is? `python prelabel.py status`.

### 5. Train

```bash
zip -qr b01.zip dataset        # upload to Drive, open train_batch.ipynb on a T4
```

The notebook checks the labels before it spends an hour on them — counts per
class, coordinates in range, and a picture of one frame with its boxes drawn.
If the boxes are not on the signs, nothing after that matters.

Nothing in the train call is a default. Two are ours: `imgsz=1280` (a sign is
30-60 px in a 2304x1296 frame) and **`fliplr=0.0`** — a mirrored `turn_left` is
a `turn_right`, and the default 0.5 trains the model to call them one class.
The rest is Ultralytics' recipe for a dataset under 1000 images: `AdamW` at
`lr0=0.001`, `mosaic=0.5`, and `epochs=50` — which is a learning-rate schedule,
not a budget, so declaring more than you run leaves the rate near `lr0` the
whole way and the model never gets its refinement phase.

## More footage later

Same loop, new id. Batch 2 does not disturb batch 1 — `build` always reads every
reviewed batch and recomputes the split, so the dataset only grows.

The useful part is the flywheel: retrain the detector on what you have, drop the
new weights in, press **score** again, and batch 3 arrives pre-annotated by a
model that has seen batches 1 and 2. `batch.json` records which detector scored
each batch, because the accept rate means nothing without it.

A batch can also be *themed* — nothing stops you picking only frames with stop
signs when a class is starving.

## Porting this to your country

One file: `../../classes.py`.

- `THAI3_NAMES` — the coarse classes your detector outputs. Any 2–5 buckets.
- `THAI_FINE_BY_PARENT` — the fine classes, grouped under the coarse class each
  belongs to. This grouping is what makes the question put to the VLM ~13-way
  instead of ~40-way, which is most of why it works at all.
- `LOOKS_LIKE` in `qwen_label.py` — one plain-English sentence per class.
  **Write these from your own footage, not from memory and not from your
  mistakes.** Writing them from an error list is tuning the prompt against your
  test set; writing them from memory gets conventions wrong (Thai
  `keep_left_or_right` is a yellow diamond, not the European blue circle).

Keep every `other_*` bucket meaning "clearly a sign, just not on this list" and
never "too blurry to tell". Conflating them teaches the model that a grey smudge
is a sign.

Then retrain a coarse detector on anything — even 300 boxes — and start at step 1.

## The checks

```bash
python prelabel.py selfcheck     # box maths, class ordering
python test_prelabel.py          # picks -> batch -> crops -> CVAT -> dataset
cd app && python test_app.py     # routes, flip semantics, batch creation
```

`test_prelabel.py` is the one that matters. Box coordinates go pixels →
normalised → CVAT → normalised → pixels → normalised again, and when that breaks
it breaks *silently*: you get a dataset full of boxes in the wrong place and a
model that trains to a plausible-looking bad number.

## Known limitations

- **Scoring is CPU-bound on a laptop** — ~0.5 s a frame at 1280px. A 600-frame
  clip is about five minutes. It runs off-thread with a progress bar, so it is
  boring rather than painful.
- **`build` splits by clip, not by frame.** Frames 2 s apart can hold the same
  physical sign, and a frame-level split would put one view in train and another
  in val and quietly inflate the score. The cost is that a class living in only
  one clip lands entirely on one side; `build` prints which classes are empty.
- **A frame holding a sign nobody could name is dropped entirely**, not used as
  background. Leaving the sign unboxed would teach the detector it is background.
- **Qwen needs a GPU you do not have locally.** 7B at 4-bit is ~5 GB of weights;
  on an 8 GB laptop it swaps. Hence the Colab hop.
- **The detector's misses are the blind spot.** A frame it calls empty, that you
  accept without looking, carries an unboxed sign into training. That is what the
  badge flip and the CVAT review of empty frames exist to catch.

## What is in here

```
app/              the picking web app (Flask) — step 1
prelabel.py       the batch CLI — everything else
qwen_label.py     runs on Colab, inside crops.zip
build_qwen_nb.py  emits qwen_batch.ipynb, so the notebook diffs like code
batches/          one folder per batch; everything about it lives inside
golden-experiment/  the frozen proof-of-concept this grew out of, and its numbers
```

`golden-experiment/` is a different, earlier pipeline: it tracked signs across
video frames instead of letting a human pick them. It is kept because its
measurements are real, and `JOURNAL.md` in there is an honest record of what went
wrong — including the two bugs that this pipeline is shaped to avoid.
