# autolabel — fine-grained Thai sign labelling

Goal: turn the 3-class detector into a **fine-grained** dataset, so a STOP sign
is labelled `stop` and not just `Regulatory`.

Doing that by hand means drawing thousands of boxes. This pipeline uses the
model you already trained to do the boring parts, and keeps you in the loop
twice so the model never has the last word.

```
[1] model watches the whole video, follows each sign, picks its clearest frame
[2] YOU fix the boxes and coarse class in CVAT
[3] VLM says which specific sign it is
[4] YOU check the VLM's answers
[5] the confirmed answer is copied onto every frame that sign appeared in
```

Steps 1, 3 and 5 are automatic. Steps 2 and 4 are you and your friend.

---

## The idea, in plain words

A 3-minute dashcam clip is **5400 frames**. The obvious approach is to grab a
screenshot every few seconds and label those. That is what the current dataset
did — a screenshot every 225 frames (7.5 seconds).

Here is the problem. Watch one STOP sign go past:

```
second  8   ▫   appears far ahead        17 px
second 10   ▪   getting closer           40 px
second 12   ■   right in front of you    98 px   ← clearest
second 13       gone, you drove past it
```

Screenshots at second 7.5 and second 15 give you a 15 px speck, or nothing at
all. Every sign that appears and passes *between* two screenshots is lost
entirely — at 7.5-second spacing you are blind for about 150 m of road at a time.

That is why the current dataset only has ~16 signs per clip.

**Instead, let the model watch all 5400 frames.** It is a computer; it does not
get bored, and it takes about 2 minutes. As it watches it follows each sign
across frames and gives it an ID, and it remembers which frame was the clearest.
Then it hands you only that frame.

> Like filming a friend walking toward you, then picking the one frame where
> their face is clearest — instead of taking a photo every 10 seconds and hoping.

**Measured on `2026_0912_013522.MP4` (3 min, 5400 frames):**

| | screenshot every 7.5 s | model watches everything |
|---|---|---|
| Signs found per clip | ~16 | **66** |
| Typical crop size | 41 px | **84 px** |
| Computer time per clip | 0 | ~2.5 min |

**4x more signs, from footage you already have.** Not because the model got
better — because you stopped throwing away 99% of the video.

---

## Where things go

```
autolabel/
├── README.md              # this file
├── gold.py                # [0] make the labelling folders / score the result
│   └─ work/gold/labels/sort_gold.py   # click-to-label GUI, run it from there
├── track.py               # [1] video -> tracks -> best frame per sign -> CVAT zip
├── cvat.py                # read a CVAT export / write a CVAT-importable zip
├── crops.py               # [3a] CVAT export -> upscaled crops + manifest
├── classify.py            # [3b] crops -> fine class, via Claude Opus 5 (local)
├── classify_qwen.ipynb    # [3b] same job, via Qwen2.5-VL-7B (Colab, needs GPU)
├── propagate.py           # [5]  confirmed labels -> every frame of each track
├── test_autolabel.py      # the one runnable check
└── work/                  # gitignored scratch: frames, crops, zips, predictions
```

**The fine class list does not live here.** Put it in
`experiments/traffic-sign_recognition/classes.py` as `THAI_FINE_BY_PARENT` —
that file is already the single source of truth for label sets, and both the VLM
prompt and any future training should read the same dict.

**The handoff file.** `crops.py` writes `work/crops/manifest.json`. Both VLM
scripts read it and write `work/predictions.json`. Same input, same output,
different model — so swapping Qwen for Opus is swapping one script, and running
both gives you a comparison for free.

---

## Step 0 — build the gold set (do not skip)

A gold set is an **answer key**: 150 crops that you label by hand, before you
see any model output.

Think of writing an exam answer key *before* grading rather than after. If you
mark while looking at the student's answer you go "eh, close enough" — and the
same thing happens when you review a label a model already filled in. Studies on
model-assisted labelling find that reviewing pre-filled labels misses **more than
half** the errors actually present. Without an answer key you end up with a
dataset that *feels* verified and is not.

> **Ordering note:** step 0 needs crops, and crops come from step 1. So run
> step 1 on 2-3 clips first (it is fully automatic, ~8 minutes), build the gold
> set from those, and only then decide whether to run the rest of the pipeline.
> Use crops from step 1 rather than from the old hand-annotated dataset — those
> are ~41 px, while real pipeline crops are ~84 px, so the old ones would be an
> unfairly hard test.

### The recipe

**1. Get 150 crops.** Run step 1 on 3 clips (~200 signs), pick 150 at random.
Name them so they give nothing away:

```
work/gold/crops/crop_0001.jpg ... crop_0150.jpg
```

Not `stop_0001.jpg`. The point is to go in blind.

**2. Make the folders:**

```bash
python gold.py init --dir work/gold --annotators <you>,<friend>
```

Generated from `classes.py`, so a folder name can never drift from a class name.
Each of you gets your own copy of the crops in `_unsorted/` — Finder *moves*
files within a volume, so a shared pile would empty out for whoever labels
second. When your `_unsorted/` is empty you are done.


```
work/gold/<your-name>/        work/gold/<friend-name>/
  stop/                         stop/
  give_way/                     give_way/
  speed_limit/                  speed_limit/
  ...                           ...
  other_regulatory/             other_regulatory/
  too_small/                    too_small/
  dont_know/                    dont_know/
  not_a_sign/                   not_a_sign/
```

See **When you cannot give it a normal class** below before you start — the last
four folders are not interchangeable.

**3. Both of you label them all, separately, without talking.**

```bash
python work/gold/labels/sort_gold.py
```

Pick your name, then click the class for each crop. `u` undoes a misclick — use
it, because a misclick writes a wrong entry into the answer key and every later
accuracy number is measured against that key. The GUI reads the folders as its
config: whoever has a directory is a labeller, and their subfolders are the
class list, so it never drifts from `classes.py`.

(Dragging files in Finder works too — the folder name is the label either way.)

If you genuinely cannot tell, use `unsure/`. Do not guess: a guessed answer key
is worse than no answer key.

Both of you do all 150 rather than splitting 75/75, because of what step 4 gives
you.

**4. Compare the two sets.** Two things fall out:

- Where you agree, it is settled.
- **How often you agreed is your ceiling.** If two humans only agree 85% of the
  time, no model can meaningfully score above 85% on this task — past that you
  are measuring noise. Report this number; it is what makes the VLM score
  interpretable.

**5. Score it:**

```bash
python gold.py score --dir work/gold
```

Prints the agreement rate (your ceiling), writes `answer_key.csv` from what you
both agreed on, and `disagreements.csv` for the rest. Settle those together, move
the files, and re-run. It also warns if `dont_know/` is non-empty, if `too_small`
exceeds 20%, and lists classes with zero examples.

```
work/gold/answer_key.csv

crop_id,    label
crop_0001,  stop
crop_0002,  speed_limit
crop_0003,  other_warning
```

That file is the gold set.

**6. Run the VLM on the same 150 crops** and compare to `answer_key.csv`.

### When you cannot give it a normal class

Four different situations, four different folders. Mixing them poisons the
answer key.

**The distinction that matters most: `other_regulatory` is not `too_small`.**

| | Meaning |
|---|---|
| `other_regulatory` | "I can see it perfectly. It is a real sign. It is just not one of our 8." |
| `too_small` | "I cannot see it well enough to say anything." |

Put blurry crops in `other_regulatory` and you teach the model that *grey smudge
= other_regulatory*. It will then fire that class on every distant blob, and you
will not notice until the results look strange.

**`not_a_sign/`** — shop banner, taillight, reflection. This is a *detector*
mistake, not a VLM question; in the real pipeline you delete these in step 2, so
they never reach the VLM. Remove them from the gold set before scoring, but
count them: that count is the detector false-positive rate at `conf 0.15`. Over
~30% means raise the threshold.

**`too_small/`** — it is a sign, but unreadable. Keep it in the gold set; the
correct answer is **abstain**. This measures something valuable: does the VLM
know it cannot tell, or does it guess confidently? Recall that the detector
scores 0.78 confidence on 20 px smudges — confident guessing on garbage is the
failure mode to watch for.

> Before giving up on a crop, open the context version (`crop_0042_ctx.jpg`).
> The wider view often settles it. Rule of thumb: squinting for more than ~10
> seconds means `too_small`.

**`dont_know/`** — you can read it, you just do not recognise the sign. That is a
you problem, not a data problem. Look it up in the Thai DOH sign manual or ask
someone. **`dont_know/` must be empty when you finish**, or your answer key has
holes in it.

| Folder | In the gold set? | Correct VLM answer |
|---|---|---|
| `stop`, `give_way`, ... | yes | that class |
| `other_regulatory` etc. | yes | `other_regulatory` |
| `too_small` | yes | **abstain** |
| `dont_know` | must be empty | — |
| `not_a_sign` | no — excluded, counted separately | — |

**Health check: if more than ~20% of crops land in `too_small`, stop and fix
step 1 before scoring anything.** The point of tracking is to hand you the
closest frame of each sign. If most crops are still unreadable, peak-frame
picking is not working — wrong `--imgsz`, fragmenting tracks, or too coarse a
`--vid-stride`. Otherwise you are measuring your frame selection, not the model.

### What the number means

| VLM accuracy | Meaning | Action |
|---|---|---|
| ≥ 85% | Reliable | Run the pipeline; step 4 is spot-checking |
| 60-85% | Useful but often wrong | Run it, but review **every** crop |
| < 60% | You would spend longer fixing than labelling | Stop and hand-label |

Compare it against your human ceiling too: 87% against a 90% human ceiling is an
excellent result, not a mediocre one.

This number is also your headline for the thesis. *"Qwen2.5-VL reached 71%
against a 93% human ceiling on Thai fine-grained signs"* is a finding.
*"We used a VLM"* is not.

---

## Step 1 — the model watches the videos

```bash
python track.py --footage ../../dataset_builder/footage --out work/pass1 \
                --conf 0.15 --imgsz 1280 --vid-stride 3
```

Ultralytics does the tracking natively (`model.track(..., persist=True,
tracker="bytetrack.yaml")`) — do not write your own tracker.

For each track it picks the frame where the box is largest, and exports just
those frames as a CVAT-importable zip.

**Point this at the 16 clips you have NOT annotated yet.** There are 42 clips in
`dataset_builder/footage/` and only 26 are in the dataset. Automation only helps
with work you have not already done — running this over frames you hand-labelled
months ago produces nothing.

(Four clips in the dataset have no footage file here: `2025_1230_004245`,
`20260908_184333_REC_F`, `20260909_115404_REC_F`, `20260909_115504_REC_F`. Worth
finding out where those went.)

**Settings, and why:**

- `--conf 0.15` — much lower than you would use for inference. A false box is one
  click to delete; a sign the model never proposes is one you will never find.
  Recall over precision here.
- `--imgsz 1280` — the size the model was trained at. It finds ~25% more signs
  than 640 and picks them up from much further away (some tracks run 17 px →
  98 px). 16 clips is about 40 minutes of compute. Run it over lunch.
- `--vid-stride 3` — process every 3rd frame. At 30 fps that is still 10
  samples per second, which is plenty for the tracker to follow a sign.

**Also export ~5 random frames per clip as a recall audit.** Signs the model
never detects in *any* frame never reach CVAT, and you would never know. Check
those random frames by hand for missed signs — that gives you a false-negative
rate to report.

**Drop tracks with fewer than 3 detections.** About 30% of raw tracks are single
spurious detections at `conf 0.15`.

## Step 2 — you fix the boxes

Import the zip into a new CVAT task. You and your friend:

- delete boxes that are not signs
- fix wrong coarse classes
- draw signs the model missed (especially in the audit frames)

**Agree on the box convention before you start** and write it at the top of the
CVAT task description. Tight to the sign face, excluding the backing plate. The
current dataset is inconsistent about this and it costs mAP50-95 (see the main
dataset README).

Export as **COCO 1.0** when done.

## Step 3 — the VLM names each sign

### 3a. Make the crops

```bash
python crops.py --coco work/pass2/instances_default.json --out work/crops
```

Cut out each box, upscale to ~448 px (Lanczos), and save a wider context crop
alongside the tight one — VLMs read signs noticeably better with some road
visible around them. Write `manifest.json` linking each crop back to its box.

No zoom-in trickery needed: because step 1 picked the closest frame, the crops
are already big.

### 3b. Classify

**Qwen path (try first, it is free):** open `classify_qwen.ipynb` in Colab. Two
things will bite you:

- **7B in bf16 is ~16.5 GB and will NOT fit a free T4.** Load in 4-bit with
  `bitsandbytes` (~6 GB, fits fine), or pay for an L4/A100.
- **Set `min_pixels` / `max_pixels` on the processor.** Qwen2.5-VL resizes
  images dynamically and the default will shrink your crops back down. This is
  the single biggest accuracy lever for small signs.

**Opus path (fallback):**

```bash
python classify.py --manifest work/crops/manifest.json --out work/predictions.json
```

Either way:

- Show the model **only the candidates for that crop's coarse class.** A
  Regulatory crop never sees the Warning options. That is what step 2 bought you
  — it cuts the decision from ~27 ways to ~9.
- Always include **`other_*`** and an **abstain** option, so the model is never
  forced to guess.
- Get confidence from **agreement across 5 samples**, not by asking the model how
  confident it is. Self-reported LLM confidence is not calibrated; agreement rate
  is.

## Step 4 — you check the names

`cvat.py` writes the predictions back into a CVAT-importable zip.

Sort by confidence and **review the low-agreement crops first** — that is where
the errors are. If step 0 came out ≥85%, spot-check the confident ones rather
than opening all of them.

## Step 5 — copy the answers back

```bash
python propagate.py --predictions work/predictions.json --tracks work/pass1/tracks.json \
                    --out work/dataset
```

**This is where the pipeline pays off.** Sign #17 was seen at 17 px, 40 px and
98 px. You read it once at 98 px and said "stop". All three sightings now get
the label `stop`.

You could never have labelled that 17 px crop by hand — you cannot see what it
is. But the tracker knows it is the same sign, so it gets the right label for
free. That gives you correct training data for **distant signs**, which is
exactly what matters for driver assistance, since spotting a sign early is the
whole point.

---

## Things the model gets wrong, and what to do about it

Measured on `2026_0912_013522.MP4`, 59 tracks with ≥3 detections.

### The coarse class flips mid-track

The same sign can be called `Warning` at second 8 and `Information` at second 12.
This happens on **8 of 59 tracks (14%)**.

**It does not hurt you.** The tracker keeps it as one sign anyway — the class
changes, the ID does not. You confirm the class once at the close-up frame, and
step 5 overwrites every other sighting with your answer. The flip erases itself.

How often a detection disagrees with its own track's close-up view:

| Sign size | Disagrees |
|---|---|
| under 30 px | 2.7% |
| 30–60 px | **14.7%** ← the confused zone |
| 60–100 px | 3.6% |
| **over 100 px** | **0.0%** |

Over 100 px the model never changed its mind once, in 105 detections. The
close-up frame is a trustworthy judge — it agreed with the whole-track majority
vote **54 times out of 59**.

Treat a flip as a **warning light**: those signs confused the model, so put them
at the top of your review pile.

### Confidence lies about small signs

| Sign size | Median confidence |
|---|---|
| under 30 px | **0.78** |
| 30–60 px | 0.90 |
| over 100 px | 0.88 |

A 20 px sign — a grey smudge you personally cannot identify — still scores 0.78.
The model is confidently guessing.

**So filter by pixel size, not by confidence.** `if longest_side > 60` is a real
filter. `if conf > 0.7` would let hundreds of unreadable signs straight into your
dataset, and you would never see it happen.

---

## Decide these before writing any code

1. **The fine class list.** About 8 per coarse class plus an `other_*` fallback,
   so every crop always has a valid label. Derive it from what is actually in
   your footage — open the contact sheets in `qa/out/` and count what you really
   see. A class with three examples in your data is a class that will embarrass
   you in the results table.

   A starting point to react to, not to accept:

   - **Regulatory:** stop, give_way, no_entry, speed_limit, no_parking,
     no_left_turn, no_right_turn, no_overtaking, other_regulatory
   - **Warning:** curve_left, curve_right, crossroads, pedestrian_crossing,
     school_zone, traffic_signal_ahead, road_narrows, speed_bump, other_warning
   - **Information:** direction_sign, route_marker, hospital, gas_station,
     parking, rest_area, bus_stop, distance_marker, other_information

   Information is the fuzziest of the three — check it against real frames first.

2. **Speed limits: one class or eight?** Recommend **one** `speed_limit` class
   plus a separate numeric attribute. The sign is identical except the number, so
   splitting it gives you eight thin classes instead of one solid one.

3. **The box convention** (step 2). Write it down before annotating.

---

## The check

```bash
~/miniconda3/envs/w124-dash-env/bin/python -m pytest test_autolabel.py
```

`test_autolabel.py` asserts two things, because these are the places a silent bug
would corrupt the dataset without anything visibly failing:

1. A round trip (CVAT export → crops → predictions → CVAT zip) puts every label
   back on the box it came from.
2. `propagate.py` writes a track's confirmed label onto every frame of that
   track, and onto no frame of any other track.

---

## Honest notes on scope

**How much data this actually gets you.** The existing 419 boxes are close to 419
*distinct* signs — sampling was sparse enough that only 32 of 827 box pairs in
consecutive frames overlap at all. Across ~27 fine classes that averages ~15 per
class, with the tail much thinner than the average. The 16 unlabelled clips at
~66 signs each should add roughly 1000 more.

**That is enough to train a crop classifier, not a 27-class detector.** A
classifier needs far less real data per class because you can bootstrap it with
synthetic signs warped from official templates. Plan on detect-then-classify, not
one fine-grained detector.

**The cheapest way to get more real data is to drive and record more footage.**
Two hours on varied roads will do more for your class coverage than another week
of engineering.

**Boxes outside the reviewed frame are not human-verified.** Only the close-up
frame gets checked in step 2; the other frames in a track carry model geometry.
That is an acceptable trade for the volume, but record it as a known limitation
alongside the existing box-border note.
