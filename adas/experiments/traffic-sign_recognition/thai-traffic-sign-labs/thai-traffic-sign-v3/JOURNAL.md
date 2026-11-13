# Traffic sign v3 — lab journal

v3 splits the old single model in two: **M1** finds *where* a sign is, **M2**
says *which* sign it is. See `note.txt` for the design.

---

## 2026-11-13 — M1: what size should the training floor be?

### Question

M1 is class-agnostic: one class, `sign`. A sign enters frame far away and grows
as the car drives at it. We decided M1 does **not** need to catch it in the
far-away stretch — catching it once it is clearly a sign is enough, because M2
cannot read a 12 px crop anyway.

So: where do we cut the training labels so M1 learns what a sign looks like
instead of learning to fire on horizon smudges?

### Setup

Three runs, b01's recipe unchanged (`yolo26n.pt`, imgsz 1280, 50 epochs,
AdamW lr0=0.001, mosaic=0.5, fliplr=0.0, batch 8, seed 0). The **only**
difference is the training-label size floor, measured in pixels at the network
input.

Boxes under the floor are deleted from the label file but the frame stays, so
the model learns the smudge is background.

| run | floor @1280 | = source px | train boxes |
|---|---|---|---|
| `floor00` | none | — | 982 |
| `floor16` | 16 px | 29 px | 627 |
| `floor24` | 24 px | 43 px | 377 |

All three scored on the **same** 163 val boxes (≥ 24 source px — the smallest
crop M2 can read). Letting each run keep its own filtered val set would make a
high floor look good for free: you deleted the hard questions.

Built by `build_m1.py`, trained by `m1_batch.ipynb` (generated from
`build_m1_nb.py`) on a Colab T4.

### Results

| run | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|
| floor00 | 0.906 | 0.632 | 0.796 | 0.666 |
| **floor16** | 0.903 | **0.689** | **0.814** | **0.684** |
| floor24 | 0.856 | 0.607 | 0.727 | 0.591 |

Noise floor: 163 val boxes, so one missed sign ≈ 0.6% recall. Gaps under ~3%
are not real.

### Conclusion

**floor16 wins — 16 px at imgsz 1280, i.e. 29 px in the source frame.**

1. **Cutting the horizon smudges helped.** +5.7pp recall over keeping
   everything, about 9 more signs out of 163 — past the noise line. Deleting
   355 tiny boxes made the model *better* at the signs that matter.

2. **Cutting further hurt.** floor24 lost on every metric. At 377 training
   boxes it is starved. Past some point data volume beats label purity, and
   that point sits between 29 and 43 source px.

3. **The precision hypothesis was wrong.** We expected the floor to suppress
   false positives. floor00 and floor16 tie on P (0.906 vs 0.903) — the entire
   gain is recall. The small boxes were not causing FPs, they were diluting the
   training signal.

### What this does not solve

R = 0.689 means M1 still misses **1 in 3** signs M2 could have read. No floor
setting fixes that; it is a data problem — 982 training boxes is thin for a
detector. More footage is the lever, not more hyperparameters.

Caveat in our favour: this is per-frame recall. A sign appears across many
frames, so per-sign recall over a track is higher. We have not measured that
yet and probably should, since "catch it once" is the actual requirement.

### Open / next

- [ ] Measure **per-sign (per-track) recall**, not per-frame. That is the
      number the design actually cares about.
- [ ] Re-run floor16 with `fliplr=0.5`. b01 kept it off because a mirrored
      `turn_left` is a `turn_right` — with one class that reason has expired
      and mirroring is free data. Held off here to avoid moving two variables
      at once.
- [ ] Re-run the floor sweep once new footage lands. The 29/43 px boundary was
      found on 982 boxes and may move with more data.
- [ ] `keep_right` has **zero** labels in b01 — collect or drop it from M2.

---

## 2026-11-13 — M2: brainstorm, PAUSED on data

Not an experiment. A design session that stopped before any run, because the
blocker turned out to be footage, not model choice. Written down so the next
session starts here instead of re-deriving it.

### Decisions made

1. **Output is driver-facing.** The dash shows the sign's name and plays a
   notification. The sound gets chosen after M2 works.
2. **`information` stays a class.** M2 says "information"; reading what the
   blue board actually says is a separate pipeline later
   (`../../thai-text-information-reader/`). So M2 is 13 classes, not 12.
3. **Training data is synthetic**, same play as `speed_limit_classifier/`.
4. **M2 must be able to say "not a sign."** Silence or an explicit reject
   class — not "name the closest match." M1 runs at P=0.903, so roughly 1 box
   in 10 that reaches M2 is a lamppost.
5. **Paused to collect more footage first.** See the shopping list below.

### What carries over from `speed_limit_classifier/`, and what doesn't

That model trained on synthetic signs only and scored **86.8%** on real crops
it had never seen. The precedent is real. But only half of it transfers:

- **`degrade()` transfers whole.** Perspective skew, light, downscale to a real
  crop size, blur, motion smear, JPEG, backgrounds cut from our own frames.
  None of it cares which sign it is wrecking. It is also where that model's
  accuracy came from, and where all four of its documented bugs lived.
- **`render()` does not.** It draws exactly one thing: red ring, white field,
  digits. Thirteen classes means arrows, curves, a pedestrian, a bus. Likely
  cheaper to feed official sign artwork through `degrade()` than to draw
  pictograms in PIL — Thai signs are a published standard. **Untested guess.**
- **Negatives are free.** Random crops from our own frames with no box in them,
  straight through the same background loader. That is the reject class.

### The structural surprise

Synthesis is strongest exactly where we are poorest. `stop` (2 boxes),
`no_right_turn` (2), `turn_left` (4) are rigid drawn standards — ideal to fake.
`information` (317 boxes) is *not* one drawing; it is a family of blue boards
with arbitrary content — impossible to fake, and the one class where we already
have plenty.

So M2's training set is **mixed**: synthetic for the 12 pictogram classes, real
for `information`. The speed classifier never had to do that, and its clean
"train synthetic / test real" split does not survive the mix. Needs thought.

### Why it is paused

Unique **clips** per class is the ceiling on unique physical signs — one sign
repeats across frames inside a clip. At the ≥24 px readable gate:

| class | boxes ≥24px | unique clips |
|---|---|---|
| information | 230 | 37 |
| speed_limit | 38 | 21 |
| keep_left_or_right | 19 | 12 |
| left_curve | 13 | 6 |
| keep_left | 5 | 5 |
| turn_left | 4 | 3 |
| turn_right | 5 | 2 |
| no_right_u_turn | 3 | 2 |
| right_curve | 3 | 2 |
| no_left_turn | 3 | 1 |
| stop | **1** | 1 |
| no_right_turn | **1** | 1 |
| keep_right | **0** | 0 |

`stop` has one readable crop in the whole dataset. So does `no_right_turn`.
Those cannot score 86% or 50% — they score 0% or 100%, and neither number means
anything.

Synthetic data fixes the **training** hole for all 13 classes. It does nothing
for the **measurement** hole. We could train 13 and honestly report on about 4.

### Footage shopping list

Not a dashcam campaign — a deliberate route past the signs we are missing.
Priority order, worst first:

- [ ] `keep_right` — 0 examples. Collect, or drop the class.
- [ ] `stop`, `no_right_turn`, `no_left_turn` — 1 readable crop each.
- [ ] `right_curve`, `no_right_u_turn`, `turn_right` — 2 clips each.
- [ ] `turn_left` — 3 clips.
- [ ] `keep_left` — 5 clips, and only 5 of its 12 boxes clear 24 px.

Rough target: ~10 distinct physical signs per class makes a per-class number
mean something. Film each from a distance so the crop-size range is covered,
not just one close-up.

### Correction to `note.txt`

`note.txt` plans an M2 "input size sweep: 24, 32, 48, 64 px" and ties the usable
pool to it. Two separate things are tangled there:

- **Network input size.** `speed_limit_classifier` already measured this:
  64 px → 128 px took real accuracy **72.2% → 91.7%**. MobileNetV3-Small
  downsamples 32×, so 64 px input leaves a 2×2 final feature map with nowhere to
  encode fine shape. If M2 uses the same backbone, that whole sweep range sits
  below the known-good point. Start at 128.
- **The source-px gate** (below which M2 declines) is a different number, set by
  eyeballing a contact sheet — the speed classifier put it at 32 px.

Also: with synthetic training, "a box is usable if its source crop ≥ the target
input" stops constraining anything. The pool only limits the **test** set now.

### Open when we resume

- [ ] Does artwork-through-`degrade()` transfer for pictograms the way drawn
      digits did? That is the one real unknown. Spike it on 3 easy classes
      before building all 13.
- [ ] How to split train/test once `information` must train on real crops.
- [ ] Reject class vs. confidence gate — the speed classifier used a gate and
      listed the missing reject class as a known limit. Do it properly here.
- [ ] Where the official Thai sign artwork comes from, and whether it matches
      what is actually on the road.

---

## 2026-11-13 — autolabel v2: M1 picks the frames

The old pipeline's first step was a human scrolling a contact sheet choosing
frames. It worked, but the frames it produced were full of the same sign three
or four frames apart, because the only ruler available was time. M1 exists now,
so it can do the choosing — and it has a ruler time never had.

### Not a new pipeline

The instinct was `autolabel-v2/` with three fresh scripts. Reading `prelabel.py`
properly killed that: `detect`, `to-colab`/`from-colab`, `to-cvat`/`from-cvat` and
`build` already work, already have a selfcheck, and `not_a_sign` was already a
reviewer verdict. v2 is **two pieces bolted onto a pipeline that already runs**:

- `app/frames.py: pick()` — replaces `extract()`'s sample-every-N-seconds. Writes
  the same `frames.json` + `scores.json`, so `prelabel.py new` eats it unchanged.
- `review.py` — step 4, naming crops, which genuinely did not exist.

Nothing was reordered. `review.py` edits `predictions.csv` in place between
`from-colab` and `to-cvat`, so CVAT receives labels a human already confirmed and
the CVAT pass becomes purely "is this a box, is it tight?" — a far faster question
than picking one of 25 names while squinting at a sign 30 px wide.

### The rule, and the two versions of it that were wrong

**Dedupe by size, not by time.** You drive past a sign over about three seconds,
so a one-second interval still yields three near-identical pictures. What makes
two frames worth reviewing separately is the sign being a different *size* —
scale is the hardest axis for a detector and the one sampling by clock is blind
to.

**First try: three fixed size bands** (16/25/39 px at the network input). Wrong.
A sign sitting near an edge flips bands on a one-pixel change and buys a second,
identical frame. Measured on 700 frames: 40 picks, 7 of them adjacent.

**Second try: a growth ratio.** A sign earns a frame once it is 1.5× bigger than
when it was last kept. No edges, so nothing to jitter across. Same 700 frames:
32 picks, 3 adjacent. Full clip: 131 → 118 frames, adjacent picks 15 → 4.

**Then: edge-clipped crops.** Driving past a sign makes it bigger *and* pushes it
out of frame, so "keep the biggest view" reaches for the last instant before the
sign leaves — half of it already gone. `id1` went 33 → 53 → 75 → 92 → **100 px
reading `ดรินทร์ / dra Road`**. M1 does not mind: a clipped sign is a normal
thing for a detector to see. M2 does: half a `no_left_turn` is not a small
`no_left_turn`, it is a red arc. `touches_edge()` now bars a cut box from earning
a frame. 118 → 114 frames, and `id381`'s ladder went from a clipped 104 px top
end to a clean 95 px.

Each of the three was found by **looking at the pictures**, not at a metric. Same
lesson as `speed_limit_classifier/`'s four bugs.

### Confidence is deliberately low

`conf=0.15`, not the 0.5 that ships. A detector only ever surfaces the signs it
already finds, so at its operating point it can never show you its own misses —
and the labels it produces quietly teach it to keep missing them. The growth rule
is what makes that affordable: a lamppost tracked across 200 frames still only
costs three frames. The junk it does surface is not waste either — a box the
reviewer deletes is a *hard* negative, far better than a random crop of road, and
that is M2's reject class built from work already being done.

### Measured, on `sign_beep/test-clip-2.mp4` (1920×1080, 4609 frames, 2.5 min)

| | |
|---|---|
| frames picked | 114 of 4609 |
| adjacent picks (≤2 frames apart) | 4 of 113 |
| boxes | 198 |
| distinct tracks | 82 |
| edge-clipped boxes still recorded | 2 (shown to the reviewer, never earn a frame) |

Verified end to end: `pick` → `new` (198 boxes carried, **0** frames needing
re-detection) → `detect` (198 crops) → `review.py` (scripted keystrokes: accept,
`not_a_sign`, `dont_know`, and typing `sto`+ENTER resolving to `stop`). The Qwen
hop is unchanged and untested here because it runs on Colab.

### The 10× that was sitting there the whole time

**ultralytics defaults to CPU on macOS even with MPS available.** `select_device()`
returns `cpu`. Measured on the same clip: **1.8 frames/s → 17.9 frames/s**. A
10-clip batch drops from ~2.8 hours to ~17 minutes. This was never about tracking
— it had been costing every detector run in this pipeline. One `best_device()` now
feeds `score()`, `pick()` and `prelabel.py detect`.

### Numbers that mean something, and one that does not

`scores.json` now records the **track id** per box. That is the only thing that
says "these boxes are the same physical sign", and it replaces counting unique
*clips* — the proxy the M2 entry had to lean on — with counting unique *signs*.
When the new footage lands, re-count the M2 pool that way.

Note that 82 tracks on one clip is a count of *candidates*, not signs. Two of the
longest-lived are wing mirrors and one is a green road marking. The number only
becomes real after the CVAT pass.

### Open

- [ ] **Edge-clipped boxes survive into the dataset.** Correct for M1, poison for
      M2. Whatever script eventually cuts M2's training crops needs the same
      `touches_edge()` check. Nothing enforces this yet.
- [ ] `review.py` has never been driven by a human through its real cv2 window —
      only by scripted keystrokes.
- [ ] `GROWTH = 1.5` and `conf = 0.15` were chosen by argument, then sanity
      checked on one clip. Worth revisiting once a reviewer has actually sat
      through a batch and can say whether it felt redundant or thin.
- [ ] The 720p question from earlier the same day: M1 is unaffected (it already
      downsamples 2304 → 1280×720), M2 loses 1.8× of crop size. Film closer.
