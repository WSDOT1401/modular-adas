# autolabel — build a fine-grained traffic-sign dataset from dashcam video

Turn dashcam footage into a YOLO dataset where a STOP sign is labelled `stop`,
not just `Regulatory` — without drawing thousands of boxes by hand.

It is built for Thai signs but nothing here is Thai. Swap the class list and the
detector weights and it builds the dataset for your country. See
**[Porting this to your country](#porting-this-to-your-country)**.

| | |
|---|---|
| **Input** | dashcam clips + a coarse sign detector you already trained |
| **Output** | a YOLO dataset (`images/`, `labels/`, `data.yaml`) with fine classes |
| **Human cost** | one click per *sign*, not per *frame* |
| **Measured on 35 Thai clips** | 376 signs reviewed by hand → 2,456 labelled boxes |

Measured numbers for this dataset live in **[RESULTS.md](RESULTS.md)**.
Why it is built this way, and what we tried that failed, lives in
**[JOURNAL.md](JOURNAL.md)**.

---

## The core idea

A 3-minute clip at 30 fps is 5,400 frames. Everyone's first instinct is to grab
a screenshot every few seconds and label those. Watch one sign go past and you
can see why that fails:

```
second  8   ▫   appears far ahead        17 px
second 10   ▪   getting closer           40 px
second 12   ■   right in front of you    98 px   ← the only readable frame
second 13       gone
```

Screenshots at second 7.5 and second 15 give you a 15 px speck, or nothing.
Every sign that appears *between* two screenshots is lost completely.

**So let the detector watch all 5,400 frames.** It follows each sign across
frames, gives it an ID, and remembers which frame was closest. It hands you only
that frame — one picture per sign, the clearest one.

Then the payoff: you label that one clear frame, and the label is copied back
onto **every frame the tracker followed that sign through** — including the
17 px frames you could never have labelled by hand. Those distant examples are
exactly what matters for driver assistance, where seeing a sign early is the
whole point.

```
one human click  ──►  6.5 labelled boxes, at every distance   (measured)
```

---

## Where the humans are

This is a human-in-the-loop pipeline, not an automatic one. There are exactly
two human passes and they do different jobs:

```
                                    ┌─────────────── automatic ───────────────┐
  footage ──► track.py ──► crops ──►│                                         │
                                    │                                         │
  ╔═══════════════════════════════╗ │                                         │
  ║ PASS A — blind labelling      ║ │   once, on your first ~400 crops        │
  ║ sort.py  (no model answers)   ║ │   builds the answer key + the ceiling   │
  ╚═══════════════════════════════╝ │                                         │
                                    │                                         │
            classify.py run ────────┤   VLM proposes a fine class per crop    │
                                    │                                         │
  ╔═══════════════════════════════╗ │                                         │
  ║ PASS B — review               ║ │   every batch after that                ║
  ║ sort.py   (fast, solo)        ║ │   Enter = accept, click = correct       ║
  ║ cvat.py   (group, fixes boxes)║ │   the model's guess is the default      ║
  ╚═══════════════════════════════╝ │                                         │
                                    │                                         │
            propagate.py ───────────┘──► YOLO dataset
```

**Pass A is the expensive one and you do it once.** Two people label the same
crops independently, seeing no model output. That gives you two things: an
*answer key* to grade models against, and an *agreement rate* — how often two
humans agreed, which is the ceiling no model can meaningfully beat.

**Pass B is the one that saves you work, and it is every batch after the first.**
The same tool, but each crop arrives with the VLM's answer already chosen. Enter
accepts it; clicking a class corrects it. Nineteen choices collapse into one
keypress for every crop the model got right.

> `sort.py` logs every accept and correction to `review_log.csv`, and
> `gold.py score` prints the accept rate. **That percentage is your real
> labour-saving number** — not the VLM's offline accuracy, which was measured on
> crops nobody had to fix.

Pass B never runs unsupervised. The model's answer is a *default*, not a label.

---

## Requirements

```bash
pip install ultralytics opencv-python pillow      # tkinter ships with Python
```

* A coarse detector (`best.pt`) trained on your own signs — 3 classes is enough.
  This pipeline finds and follows signs with it; it does not need to know which
  sign is which.
* `classes.py` two directories up, defining `THAI_FINE_BY_PARENT`. One source of
  truth for the label set: the folder names, the VLM prompt and `data.yaml` all
  read it, so they cannot drift apart.
* A GPU only for the VLM step (`classify.py run`, ~6 GB). Free Colab T4 works.
  Everything else runs on a laptop.

---

## Step 1 — the detector watches the videos

```bash
python track.py --footage footages --out work/pass1 \
                --conf 0.15 --imgsz 1280 --vid-stride 3
```

Writes `work/pass1/`:

| | |
|---|---|
| `tracks.json` | every sign, every frame it appeared in — **the file everything else needs** |
| `crops/` | one tight crop per sign, at its closest view |
| `crops_ctx/` | the same crop with surrounding road, for when the tight one is ambiguous |
| `frames/`, `labels/`, `_cvat/` | peak frames + a CVAT-importable task, if you want to fix boxes |
| `audit/` | random frames, for counting signs the detector never proposed |

**The three settings that matter:**

* `--conf 0.15` — far lower than you would use for inference. A false box costs
  one click to delete; a sign the detector never proposes is one you will never
  find. Recall over precision here.
* `--imgsz 1280` — match what the detector was trained at. At 640 it finds ~25%
  fewer signs and picks them up much later.
* `--vid-stride 3` — process every 3rd frame. At 30 fps that is still 10 samples
  a second, plenty for the tracker to follow a sign. Budget ~2.5 min per clip.

**Open `audit/` and check it by hand.** Signs the detector misses in *every*
frame never reach you and you would never know they were missing. That count is
your false-negative rate, and it belongs in your limitations section.

---

## Step 2 — fix the boxes *(optional)*

Import `work/pass1/_cvat/` into a CVAT task to delete non-signs, fix coarse
classes, and draw signs the detector missed.

**Agree on a box convention first and write it in the task description** — tight
to the sign face, excluding the backing plate, or whatever you choose. An
inconsistent convention costs mAP50-95 and is very hard to fix later.

Skip this if your detector is good enough; the labelling pass below catches
false positives anyway, via the `not_a_sign` folder.

---

## Step 3 — PASS A: build the answer key

**You cannot skip this.** An answer key is 150+ crops labelled by hand *before
anyone sees model output*. It is the exam answer key written before grading, not
after — mark while looking at the student's answer and you go "eh, close
enough". Reviewing pre-filled labels misses more than half the errors actually
present, and you end up with a dataset that *feels* verified and is not.

```bash
python gold.py init --dir work/gold --annotators <you>,<partner>
python sort.py --dir work/gold          # both of you, separately, no talking
python gold.py score --dir work/gold
```

`init` builds one folder per class per person, from `classes.py`, and copies the
crops into each person's `_unsorted/`. Separate copies on purpose: moving a file
removes it from a shared pile, so the first person to label would empty it for
the second.

`sort.py` shows a crop and the class buttons. `u` undoes a misclick — use it, a
misclick writes a wrong answer into the key and every later number is measured
against it. `c` shows the wider context crop, which usually settles a hard one.

**Both of you label all of them, not 75/75.** The overlap is the point.

### The four folders that are not classes

Mixing these up poisons the key. The distinction that matters most:

| | Meaning |
|---|---|
| `other_regulatory` | "I see it perfectly. Real sign. Just not one of our classes." |
| `too_small` | "I cannot see it well enough to say anything." |

Put blurry crops in `other_regulatory` and you teach the model *grey smudge =
other_regulatory*. It will then fire that class on every distant blob.

| Folder | In the key? | What it means |
|---|---|---|
| `too_small` | yes | a real sign, unreadable — the correct model answer is **abstain** |
| `not_a_sign` | no, counted separately | detector false positive. The count is your FP rate at `conf 0.15`; over ~30% means raise the threshold |
| `composite` | no | the box holds a sign *assembly*, not a sign. The box is wrong, not the reading — fix it in CVAT |
| `dont_know` | **must end empty** | you can read it, you just don't recognise it. Look it up |

**If more than ~20% lands in `too_small`, stop and fix step 1** before measuring
anything. The whole point of tracking is to hand you the closest frame of each
sign. If most crops are still unreadable, peak-frame picking is broken — wrong
`--imgsz`, fragmenting tracks, or too coarse a `--vid-stride`. Otherwise you are
measuring your frame selection, not the model.

### Settling disagreements

```bash
python gold.py sheet                      # -> disagreements.png, captioned with who said what
$EDITOR work/gold/settled.txt             # "<crop_id> <class>", one per line
python gold.py apply                      # writes the agreed label into BOTH folders
python gold.py score
```

Never hand-edit one person's folder: a settlement applied to one side only
quietly keeps the disagreement.

**Report the agreement rate from *before* you settled.** After `apply` it reads
100%, which is arithmetic, not a finding. The pre-settlement number is the human
ceiling and the only one that belongs in a thesis.

### Labelling with someone remote

`work/` is gitignored, so a partner cannot pull the crops. Send their folder —
it holds the queue and nothing else, so it is blind by construction. **Never
send `work/gold/`**: it contains the other labeller's answers, and a labeller
who has seen them agrees with them.

```bash
cd work/gold
rm -rf /tmp/pack && mkdir -p /tmp/pack
cp -R labels/partner /tmp/pack/partner
find /tmp/pack/partner -type d -empty -exec touch {}/.keep \;
(cd /tmp/pack && zip -rq ../partner_labelling.zip .)
# they also need sort.py and classes.py; they run: python sort.py --dir .

unzip -o ~/Downloads/partner.zip -d work/gold/labels/      # when it comes back
python gold.py score
```

The `.keep` files matter: empty class folders *are* the button list, and some
unzip tools silently drop empty directories. Check the `labelled by both:` line
after scoring — if it is below what you sent, they labelled a stale set.

---

## Step 4 — measure the pre-annotator

Before trusting a model to pre-fill labels, find out whether it is better than
guessing.

```bash
python classify.py run   --dir work/gold --out work/predictions.csv   # GPU / Colab
python classify.py score --dir work/gold --pred work/predictions.csv  # laptop
```

`run` has two modes, and the difference matters:

| | crops processed | coarse class from |
|---|---|---|
| *(default)* | the answer key | the **human** label |
| `--unlabelled` | crops the key has no opinion on | the **detector** (91.2% right) |

The default is for **measuring** — grading the model against labels humans
already settled. `--unlabelled` is for **pre-annotating** new footage, where
there is no human label yet. Measure first; only pre-annotate with a model you
have already shown beats the baseline.

**Do not grade it on accuracy.** If one class is 56% of your key, a program that
never opens an image scores 76.6%. Grade on **macro-recall** — per-class recall
averaged with every class weighted equally, over classes with ≥5 examples.
`score` prints the blind baseline next to every number so you cannot quote one
without the other.

| macro-recall vs. the blind baseline | What to do |
|---|---|
| at or below it | the model is worthless here; report it and label by hand |
| a little above | report as a negative result — still a finding |
| well above | use it to pre-fill, and review every crop (step 5) |

Report it against the human ceiling:
*"Qwen2.5-VL reached 71.5% macro-recall against a 91.7% inter-annotator
agreement, where a class-prior baseline reaches 33.3%"* is a finding.
*"We used a VLM"* is not.

### Running it on Colab

A 7B VLM does not fit an 8 GB laptop, and in bf16 it does not fit a free T4
either. `run` loads it 4-bit (~6 GB), fp16 compute — not bf16, because the free
T4 is Turing and has no bf16 units.

```bash
rm -rf work/vlm_run && mkdir -p work/vlm_run/work/gold
cp classify.py ../../classes.py work/vlm_run/          # classes.py must sit flat alongside
cp -r work/gold/crops work/gold/answer_key.csv work/gold/source_map.csv work/vlm_run/work/gold/
(cd work && zip -qr vlm_run.zip vlm_run)
```

```python
!pip -q install -U transformers accelerate bitsandbytes
!python classify.py run --limit 2     # smoke test — version mismatches show up here
!python classify.py run               # ~25 min; resumes, so a dead session costs nothing
```

**The one setting that silently ruins the run.** Qwen picks its own input
resolution and the default *shrinks* a 448 px crop. For a sign whose identity is
one small glyph that is fatal, and it fails quietly — you just get bad numbers.
`MIN_PIXELS`/`MAX_PIXELS` floor it, and `run` prints what the model actually saw:

```
crop 1: file 448x432 -> model sees 476x448 px  (1.10x area) OK
```

Only *shrinking* matters; upscaling invents no detail but destroys none. If you
ever see `STOP`, kill the run.

---

## Step 5 — PASS B: review the pre-filled labels

Two routes. They do the same job; pick by whether the **boxes** need fixing.

| | `sort.py` | `cvat.py` → CVAT |
|---|---|---|
| speed | ~1 s per crop | slower |
| who | one person at a time | the whole group, one task |
| can fix the label | yes | yes |
| **can fix the box** | **no** | **yes** |
| records the accept rate | yes (`review_log.csv`) | no |

**Boxes are worth fixing.** Only the peak frame of each sign is ever seen by a
human; `propagate.py` then copies that box's geometry onto every other frame. A
box fixed here is fixed on all ~6 frames that sign contributes — and a sloppy one
is sloppy ~6 times.

### Route A — `sort.py` (fast, solo)

```bash
cp work/predictions.csv work/gold/predictions.csv   # sort.py switches mode on this file
python sort.py --dir work/gold
python gold.py score --dir work/gold                # prints the accept rate
```

Same tool as pass A, but each crop opens with the model's answer selected.
**Enter accepts, clicking a class corrects.** Work the whole queue — the point is
a human decision on every crop, just a much cheaper one. Every decision is
appended to `review_log.csv`, so the accept rate is measured, not estimated.

### Route B — CVAT (group, fixes boxes)

```bash
python cvat.py export --tracks work/pass2/tracks.json --frames work/pass2/frames \
                      --pred work/predictions.csv --out work/review_task.zip
```

In CVAT: **new task → create it with the labels from `obj.names` → upload the zip
→ Import annotations → format `YOLO 1.1`.** Every box arrives already named with
the model's guess. A crop with no usable prediction falls back to its coarse
catch-all rather than being left out — a box that is not in the task is a sign
nobody reviews.

Your group then fixes labels and boxes, and marks false positives `not_a_sign`
(a label, not a deletion — a missing box is indistinguishable from one nobody got
to). When done, export the task as **YOLO 1.1**:

```bash
python cvat.py import --zip ~/Downloads/task_export.zip --tracks work/pass2/tracks.json \
                      --frames work/pass2/frames --out work/reviewed.csv
```

```
work/reviewed.csv: 371 reviewed signs
  335 matched a reviewed box, 36 deleted -> not_a_sign
  25 boxes the reviewers ADDED (signs the detector missed) — not imported,
     they have no track to propagate along
```

Boxes are matched back to their sign by IoU, so a reviewer can move or retighten
one without breaking the link. **Read the "ADDED" number** — it is your detector's
false-negative count, and it belongs in your limitations.

Then file those labels into the gold workspace, because `answer_key.csv` is built
from the class folders and nothing else — a review done in CVAT has no other way
back in:

```bash
python gold.py ingest --dir work/gold --from work/reviewed.csv
```

`ingest` only moves crops still sitting in `_unsorted/`. A crop already in a class
folder was put there by a human looking at it blind, and that decision outranks
anything a model-assisted pass produced — so a later review can never quietly
rewrite the answer key an earlier one established.

---

## Step 6 — build the dataset

```bash
python propagate.py --report                       # the numbers, writes nothing
python propagate.py --out work/dataset             # extract frames + labels
```

This is where the pipeline pays off. A sign seen at 17 px, 40 px and 98 px was
read once at 98 px. All three sightings now carry the right label.

```
  376 labelled signs   18400 raw detections -> 2456 boxes on 2291 frames   (6.5x per sign)
  frames: 1841 train / 450 val   (87 dropped: train+val signs share the frame)

  class                   signs  val   boxes
  information               202   40    1381
  other_warning              69   14     407
  ...
```

Then train:

```bash
yolo detect train data=work/dataset/data.yaml model=yolo11n.pt imgsz=1280 epochs=100
```

**Three rules it enforces, because each one silently inflates a score:**

* **The split is by track, never by frame.** Two frames 0.1 s apart are nearly
  the same picture; split by frame and your validation score measures
  memorisation. Frames holding signs from both sides of the split are dropped.
* **Every sign on a kept frame gets a box.** A real sign left unlabelled teaches
  the detector that signs are background. Frames holding a sign nobody could
  name (`too_small`, `composite`) are dropped for that reason.
* **`not_a_sign` boxes stay unlabelled on purpose** — those are your detector's
  own false positives, and leaving them in the image with no box is how it
  learns to stop firing on them.

**The knobs:**

| flag | default | what it does |
|---|---|---|
| `--size-step` | `0.20` | keep a box once it has changed size by 20%. Lower = more near-duplicate frames, not more information |
| `--min-signs` | `5` | a class backed by fewer distinct signs folds into its `other_*` catch-all |
| `--val-frac` | `0.20` | share of *signs* (not frames) held out |

**`--min-signs` is the honest one.** A class with one distinct sign cannot be
learned (the model memorises that one signpost) and cannot be evaluated (one
sign goes to train or val, never both). Left in, it adds a 0.0 AP row and
overstates how many classes your dataset really covers. `--report` names every
class it folded — **read that list, it is a list of what you still need to film.**

---

## Adding more footage

Labelling is incremental: finished work is never re-queued, and a crop already
in the set is never swapped for a different picture.

```bash
# 1. new clips into footages/ (any subfolder), then track ONLY those
python track.py --footage footages --out work/pass2 --skip-done work/gold/tracks.json

# 2. fold them in and queue them for everyone
python gold.py add --dir work/gold --from work/pass2

# 3. let the VLM propose a fine class for each new crop   (Colab, see step 4)
#    --unlabelled = predict only crops the answer key has no opinion on
python classify.py run --unlabelled --out work/predictions_v2.csv

# 4. your group reviews — pick ONE route (see step 5)
cp work/predictions_v2.csv work/gold/predictions.csv     # route A: sort.py
python sort.py --dir work/gold
#   -- or --
python cvat.py export --tracks work/pass2/tracks.json --frames work/pass2/frames \
                      --pred work/predictions_v2.csv --out work/review_task.zip
python cvat.py import --zip ~/Downloads/task_export.zip --tracks work/pass2/tracks.json \
                      --frames work/pass2/frames --out work/reviewed.csv

# 5. rebuild the key and the dataset
python gold.py score --dir work/gold --solo     # --solo if only one of you labelled
python propagate.py --out work/dataset
```

**`--solo`.** `score` normally keys only crops *both* people labelled, because
the agreement rate is the point. New footage is often labelled by one person —
excluding it makes that footage useless. `--solo` keys those too, marked
`annotators=1`, and the agreement rate stays computed on two-annotator crops
alone so it is not diluted. Say in your limitations how many crops carry a 1.

**Re-measure after new footage.** The baselines are computed from the key each
time, so they move when the class balance moves. A VLM score against the old key
is not comparable to one against the new — re-run both, or state which key each
number came from.

**Why re-running is safe.** Crop ids are `<clip>_t<track>`, derived from the
source rather than a counter. A counter restarts at 1 every run, so a second
batch would emit different images under names already labelled in the first and
silently corrupt the key. Derived ids make re-running a clip a no-op.

One wrinkle: `--skip-done` skips by clip name, and a clip that produced no
labelable crops never lands in `tracks.json`, so it gets tracked again. Wasted
minutes, nothing worse.

---

## Porting this to your country

Nothing here knows what a Thai sign looks like. Three changes:

**1. Your class list** — edit `THAI_FINE_BY_PARENT` in `../../classes.py`.
Every class must belong to a coarse parent, and **every parent needs a catch-all**
(`other_*`, or the last entry in the group) so no crop is ever unlabelable.

Derive the list from what is actually in your footage, not from your national
sign manual. The manual has 300 signs; your road has 20. A class with three
examples will embarrass you in the results table.

> **Speed limits: one class, not eight.** The sign is identical except the
> number. Splitting it gives you eight thin classes instead of one solid one;
> read the number with OCR later if you need it.

**2. Your detector** — a coarse model trained on your signs. Point `MODEL` in
`track.py` at it. Three classes is plenty; this pipeline only needs it to find
signs and follow them, not to name them.

**3. Your VLM prompt** — `LOOKS_LIKE` in `classify.py` is one line of visual
description per class ("yellow diamond, a single black arrow bending right").

Write those descriptions from a contact sheet of your own crops, **before you
see any score.** If you write them by looking at what the model got wrong, you
are tuning on your test set and the number stops meaning anything. Describe
every class to the same level of detail, including the ones that already work.

---

## The checks

```bash
python classify.py selfcheck      # scoring maths, baselines, prompt/parser bugs
python propagate.py --selfcheck   # sampling, class folding, catch-all resolution
python cvat.py selfcheck          # IoU round-trip: a nudged box must keep its sign
python propagate.py --report      # the dataset numbers, without writing anything
```

---

## Known limitations — state these before an examiner finds them

* **Only the peak frame is human-verified.** Every other frame in a track
  carries detector geometry, not a human box. An acceptable trade for the
  volume, but it is a real caveat.
* **Boxes are propagated, not re-detected.** If the tracker drifted, the drift
  is in your labels.
* **2,456 boxes come from 376 signs.** Always state both. Frames 0.1 s apart are
  near-duplicates, and a bare frame count overstates the dataset.
* **The classes `--min-signs` folded away are the gap in your footage.** No
  amount of engineering fixes it. Drive and record more.
