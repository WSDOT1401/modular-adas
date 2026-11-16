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

> **Superseded by the 2026-11-15 entry.** Kept because its reasoning still
> holds: only its conclusion (pause and go film) was overtaken by a deadline.

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

---

## 2026-11-15 — M2: design settled, and seven classes pulled out of the catch-alls

Supersedes the PAUSED entry above. That one stopped because the measurement hole
looked fatal. It still exists — it just stopped being a reason not to build.

### What actually changed the design

The deadline is a **presentation next week**, and the cost of a wrong answer is
credibility in a room, not a missed sign on the road. That inverts two things:

- **"Not sure" becomes a good answer.** To a driver, silence is useless. To an
  examiner it reads as a model that knows its own limits.
- **The measurement hole is the main risk, not a footnote.** "What is your
  per-class accuracy?" is the question that always gets asked, and five classes
  answered it with n≤3.

Decision: say the hole out loud on the slide rather than paper over it.

### Decisions

6. **M2 is trained on 28 names + `not_a_sign`, and displays 13.** The other 15
   map to "dash stays quiet" — identical on screen to rejecting them, but a far
   easier thing to learn. See *the catch-all problem* below.
7. **`keep_right` stays in** at 0 real crops. Synthesis can train it; nothing can
   score it. On the road that is a right answer we would otherwise have thrown
   away; on the slide it is a blank cell with a reason. Both are fine. The
   alternative — dropping it — turns every real `keep_right` into a confident
   `keep_left`, because they are the same blue circle.
8. **Test on real crops only, split by clip.** Never on synthetic. This is the
   `speed_limit_classifier` precedent (train synthetic, test real, 86.8%) and it
   is the only split that means anything. Splitting real crops at random would
   put the same physical sign on both sides, because one sign repeats across
   frames inside a clip.
9. **Report macro-average over the 13, not micro.** `information` is 357 of 535
   readable crops in the displayed set — a micro number is mostly a report card
   on blue boards wearing a coat that says "traffic sign recognition". Print `n`
   beside every class, and print *not scored* rather than a number for anything
   under 5 real crops. A class with 2 crops can only score 0/50/100; averaging
   that into the headline gives one crop a 4-point vote.

### The catch-all problem

The first shape of decision 6 was one `other_sign` bucket for everything outside
the 13. Rejected, and the objection came from the right place: a class that is
"a pile of unrelated things" is the hardest kind to learn.

That objection is in the literature. *Reducing Network Agnostophobia* (Dhamija
et al., NeurIPS 2018) finds background/garbage classes "generally insufficient",
and proposes Entropic Open-Set loss instead — train unknowns toward a flat
softmax, so "I don't know" is *no opinion* rather than *a vote for the garbage
bin*. It beats both softmax-thresholding and a background class at low FPR.

We are **not** doing that this week: it is a custom loss and a new metric (OSCR)
with six days left. It goes on the slide as "what we would do next", which is a
better thing to say than nothing.

What we are doing instead is **Background Splitting** (Mullapudi et al., CVPR
2021): cut the catch-all into coherent subclasses and train on those. Their
reported swing is mAP 10.6 → 52.9 in the most imbalanced case. The expensive
part of their method is *inventing* subclass labels with a pre-trained model —
we skip it entirely, because CVAT already gave us real ones.

So the split ran against our own labels, by eye, off contact sheets:

| pulled out | from | readable (≥24px) |
|---|---|---|
| `chevron` | other_warning | 59 |
| `merge` | other_warning | 12 |
| `crossroads` | other_warning | 12 |
| `railway_crossing` | other_warning | 7 |
| `mandatory_direction` | other_regulatory | 15 |
| `no_pedestrians` | other_regulatory | 10 |
| `height_limit` | other_regulatory | 7 |

`chevron` was the big one and the obvious one in hindsight: ~half of
`other_warning` was a single drawing. It is also the nearest neighbour to
`left_curve`/`right_curve` — yellow, black, directional — so leaving it unnamed
put 59 distractors against their 17 real crops.

Result: the two catch-alls went **152 → 78** readable crops. Stopping rule was
~6 crops; a group smaller than that does almost no harm sitting in the bucket,
and every extra name costs a reviewer a decision on every 30 px crop they see.

Incidental: the pass turned up 2 more `stop` (8 → 10). Something real *was*
hiding in there.

### Synthetic data: the untested guess, now tested

The PAUSED entry guessed that feeding official sign artwork through `degrade()`
would beat drawing pictograms in PIL, and flagged it **untested**. Tested:

**All 12 pictogram classes are on Wikimedia Commons as SVG, Public domain,
author "Government of Thailand".** Commons renders SVG→PNG server-side, so there
is no rasteriser dependency either — one download script, no new packages.
Codes: `บ-1`/`บ-1-1` stop, `บ-6` no right U-turn, `บ-8`/`บ-9` no left/right turn,
`บ-32-N` speed limit, `บ-38`/`บ-43` turn left, `บ-39`/`บ-44` turn right,
`บ-40`/`บ-41`/`บ-42` keep left/right/either, `ต-1`/`ต-2` left/right curve.

Three things the wiki table did not say, found by rendering them and looking:

- **Three classes are two drawings each.** `turn_left` is both `บ-38` (straight
  arrow pointing left) and `บ-43` (bent arrow); `turn_right` likewise; `stop` is
  both Thai-only and bilingual. Synthesize one variant and the model learns half
  the class.
- **`degrade()` plugs in unmodified** — it takes a 256 px RGBA and uses the alpha
  channel as its paste mask. Download at **256**, and `.convert("RGBA")` on load:
  the two yellow curve diamonds come back palette-mode, and without the convert
  they paste as opaque squares and the model learns "yellow square = curve".
- **Keep `synth.py` for `speed_limit`.** The SVG `บ-32` is an idealised sign.
  `synth.py` already draws the variants copied off our own crops — yellow and
  orange backing boards, sun-bleached rings, `Km/h` subtext, red digits — and it
  scored 86.8%. Do not swap tested code for cleaner artwork.

`information` still cannot be synthesized (a family of boards with arbitrary
content, not one drawing) and does not need to be: 357 readable real crops.

### The dataset, after `prelabel.py build`

1228 frames, 1610 boxes, 953 train / 275 val (82 train clips / 20 val),
**403 background frames** for the reject class. 1309 readable crops: 535 in the
displayed 13, 774 in the helpers.

| displayed | ≥24px | clips | | helper | ≥24px |
|---|---|---|---|---|---|
| information | 357 | 46 | | no_stopping_parking | 246 |
| speed_limit | 57 | 24 | | pedestrian_crossing | 230 |
| keep_left_or_right | 22 | 13 | | chevron | 59 |
| no_left_turn | 20 | 8 | | u_turn | 56 |
| no_right_u_turn | 18 | 5 | | other_warning | 52 |
| turn_right | 15 | 5 | | other_regulatory | 26 |
| left_curve | 13 | 6 | | t_junction_left | 19 |
| stop | 10 | 5 | | reserved_for_bus | 19 |
| turn_left | 9 | 4 | | mandatory_direction | 15 |
| no_right_turn | 5 | 3 | | merge | 12 |
| keep_left | 5 | 5 | | crossroads | 12 |
| right_curve | **4** | 3 | | no_pedestrians | 10 |
| keep_right | **0** | 0 | | height_limit / railway_crossing | 7 / 7 |

Three classes cannot be scored and will not be without footage: `keep_right`
(0), `right_curve` (4), `t_junction_right` (4).

### What the pipeline had to change

Running `review.py` **after** a CVAT pass used to be a silent no-op, and we hit
it live: `review.py` writes `predictions.csv`, `build` reads `reviewed.csv`, and
the two never met. 95 renames went nowhere before anyone noticed.

- `review.py` now carries names into `reviewed.csv` on exit (`sync_reviewed`),
  limited to crops settled in that run — `predictions.csv` still holds the
  pre-CVAT guess for everything else, and syncing those would undo CVAT wholesale.
- `--only` now filters on `reviewed.csv` when it exists. It was queueing the
  stale pre-CVAT label: on b01 that meant **332 crops, 192 of them pointless**
  (87 had already had their box deleted in CVAT) while missing 27 real ones.
  Corrected queue: 165.
- `not_a_sign`/`dont_know` from a crop view are **refused and listed by name**,
  not silently dropped. A box can only be deleted in CVAT, where the whole frame
  is visible; `dont_know` is worse still, because `build` throws away the entire
  frame and every correctly-boxed sign on it.
- `review.py --selfcheck` covers the three ways the sync can go wrong.

The refusal list immediately paid for itself: 28 crops came back, and they were
not non-signs — **24 of 28 were under 24 px**, i.e. "too small to tell". Two of
the four large ones were real warning signs the refusal saved. `classes.py` had
already written this rule in October: *`other_*` means "clearly a sign, legible,
just not on this list" — never "too blurry to tell".* At 15–20 px the honest key
is SPACE, not `x`.

**Class order is now frozen.** Seven names were inserted inside their parent
groups rather than appended at the end, so indices shifted. Safe only because
nothing has been trained on `thai_fine` yet — M1 collapses all of them to one
class. M2 trains on this order, so from here, append only.

### Open

- [ ] `keep_right` 0 clips, `right_curve` 3, `t_junction_right` 2. Still the
      footage shopping list, still unchanged by any amount of synthesis.
- [ ] Edge-clipped boxes (carried over): correct for M1, poison for M2. The
      script that cuts M2's crops needs `touches_edge()`. Still nothing enforces it.
- [ ] Entropic Open-Set loss + OSCR, if M2 survives the presentation.
- [ ] The reject class has no harvester yet. `not_a_sign` boxes are preserved
      with their coordinates — exactly where M1 falsely fires at conf 0.15, which
      is the best negative set we will ever get for free. Nothing reads them.
- [ ] Yellow imbalance: chevron 59 + other_warning 52 against left_curve 13 +
      right_curve 4. Synthesis is supposed to fix this by fiat. Check the
      confusion matrix before believing it.

---

## 2026-11-15 (evening) — M1 lands at R 0.82, M2 trains at 93.6%

Both halves of v3 now have a number. The design entry above is unchanged by any
of this; what follows is what happened when it met the data.

### M1: the new footage bought recall, which is the thing that was broken

`m1-floor16-b01b02`, yolo26n, 50 epochs, imgsz 1280, batch 8, `fliplr=0`.

| run | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|
| floor16, b01 only | 0.903 | 0.689 | 0.814 | 0.684 |
| **floor16, b01+b02** | 0.852 | **0.820** | **0.876** | **0.741** |

The 2026-11-13 entry ended on *"R = 0.689 means M1 still misses 1 in 3 signs M2
could have read"*. It now misses 1 in 5.6. Precision gave back 5 points to buy
13 points of recall, which is the right trade for a detect-then-classify design:
M2 has a reject class and can throw a false box away, but neither model can
recover a sign M1 never boxed.

Caveat worth saying out loud before anyone quotes the delta: **the two rows do
not share a val set.** b01+b02 has 20 val clips where b01 alone had fewer, so
this is "the model got better" and "the exam changed" at once. The honest claim
is the direction, not the 6.2 points.

### M2: built, and it works

Four files, all of them small:

| file | what |
|---|---|
| `fetch_art.py` | 20 public-domain drawings off Wikimedia Commons, 256px RGBA |
| `m2_synth.py` | `sample(name)` -> a fresh degraded sign, drawn on demand |
| `build_m2.py` | real crops -> `m2/{train,val}/<class>/`, 1285 + 932 |
| `train_m2.py` | MobileNetV3-Small, 29 classes, 128px, ~8 min on MPS |

**128px, not 64.** `speed_limit_classifier/train.py` had already measured this
and written it down: MobileNetV3-Small downsamples 32x, so 64px leaves a 2x2
final feature map and real accuracy went 72.2% -> 91.7% by changing one number.
Reading our own notes was worth more than any architecture choice this week.

**Nothing synthetic is written to disk.** `Mixed` holds the real crops plus N
synthetic *slots*; each slot has a fixed class and draws a brand new sign every
time it is asked for. There is no fixed synthetic set to memorise and the rare
classes never run out.

**Inverse-frequency sampling over real and synthetic together.** One straight
epoch is 43% `not_a_sign` and 15% `information`; a model can score well on the
micro number while never once saying `merge`.

### The split had to change, and the reason was measurable

M1's clip split left **5 of the 13 displayed classes with no scoreable val set**
-- `left_curve` had 13 crops and every one of them was in train. Those are five
blank cells on a slide, caused entirely by where the dice landed.

So M2 picks its own clips. Two rules, in order:

1. **Every clip M1 held out stays held out.** M2's val is a superset of M1's, so
   no clip is ever in M1's val and M2's train at once, and an end-to-end demo on
   an M1 val clip is honest for both models.
2. **Then buy coverage**, rarest displayed class first, until each has 5 real
   val crops or runs out of clips.

10 of 13 scoreable, from 5. It costs train real crops of exactly the classes
that have infinite synthetic ones -- six displayed classes now have **zero** real
training crops and are trained purely on artwork. That is not a compromise, it
is the `speed_limit_classifier` result applied on purpose: `keep_left` has 0
train crops and scores 80-100%.

`build_m2.py` asserts both rules against the data on every run.

### The artwork was wrong, and only looking at the crops showed it

The design entry called the artwork question *tested*. It was half-tested: the
files downloaded and `degrade()` accepted them, which is not the same as the
drawing being the one on the road.

**The blue `b-38`/`b-43` turn signs do not appear once in our footage.** Every
single `turn_left`/`turn_right` crop is the older style -- white disc, red ring,
black bent arrow -- confirmed on a 100px crop where a prohibition bar would be
unmissable. Commons has no code for it. But `b-8`/`b-9` ("no left/right turn")
carry the identical arrow glyph under a bar, and the bar sits entirely inside
r<0.85 while the ring is >=74% of every annulus outside it. `strip_bar()`
deletes the bar; the drawing is then right. Both scored **100%**.

Same mistake, caught the same way: 14 of the 22 `keep_left_or_right` crops are
the yellow diamond `t-62`, not the blue circle `b-42`. Added. Also `t-3`/`t-4`
(the sharp-bend curves) and `b-1-2` (English-only STOP).

Lesson, and it is the same one as `other_warning` being half chevrons: **render
the thing and look at it.** A table of sign codes is not evidence about footage.

### review.py could only show two thirds of the boxes

Found while trying to review a specific crop: `prelabel.py detect` cuts one crop
per box *it proposed*, and that is the whole of `crops/`. A box drawn by hand in
CVAT afterwards has a row in `reviewed.csv` and no image on disk, so `review.py`
skipped it in silence -- **56 of b02-1's 547 boxes, including 8 of its 10
`stop`s**. `fill_crops()` now cuts them on demand, the way `detect` does, rather
than re-running `detect` and throwing away every name on the batch.

### Two label passes, and the second one was found by the model

87.0% on the first run, with one bad cell: `no_left_turn` at 50%, losing 4 of 8
to `no_stopping_parking`. Rendering those four settled it in one look -- they
are **blue discs with a red slash**. The model said "no stopping" and was marked
wrong for being right. Same confusion as the `no_right_turn` crop caught the day
before: a blue disc with a red slash keeps getting read as a turn ban.

Then the model was pointed at the whole dataset: every crop where it disagrees
with its label at >0.80 confidence. **27 out of 2217.** The labels are good.
Most of the 27 are one group -- 15 boxes deleted in CVAT that the model calls
bus-stop or information boards -- and that is a definition question (is a
bus-stop shelter a sign?), not an error. Left alone.

This is worth a slide of its own. The first number was 87%; four of its errors
were the dataset's, not the model's. **Using the trained model as a label
checker found them in one pass**, and that is a technique, not an accident.

### Where M2 stands

| sign on the dash | n | accuracy |
|---|---|---|
| no_left_turn | 12 | 100.0% |
| no_right_u_turn | 5 | 100.0% |
| turn_left | 7 | 100.0% |
| turn_right | 8 | 100.0% |
| speed_limit | 24 | 95.8% |
| information | 150 | 96.0% |
| stop | 10 | 90.0% |
| keep_left_or_right | 9 | 88.9% |
| left_curve | 7 | 85.7% |
| keep_left | 5 | 80.0% |
| no_right_turn | 4 | *not scored* |
| right_curve | 4 | *not scored* |
| keep_right | 0 | *not scored* |
| **MACRO over 10** | **237** | **93.6%** |
| dash stays quiet | 687 | 95.1% |

"Dash stays quiet" is the second number and it is not decoration: when the sign
is not one of the 13, naming the wrong helper class is invisible to a driver,
and lighting up the dash is not.

### Fixed in passing

- `build_m2.py` did not wipe its output. The split is recomputed every run, so
  the previous run's crops stayed behind and the same sign ended up in train
  **and** val -- the one thing the clip split exists to prevent. Caught because
  the trainer counted 1430/932 crops where the builder had just printed
  1347/870. Two numbers that should match, printed where they can be compared.
- `touches_edge` is done: `build_m2.py` drops any box within 2px of the frame
  border. Correct for M1, poison for M2, and it was an open item since October.
- The reject-class harvester is done: every `not_a_sign` box, which is exactly
  where M1 fires and is wrong, plus two random squares off each of the 403
  sign-free frames.

### Open

- [ ] Footage, still, and still unchanged by anything else: `keep_right` 0 clips,
      `right_curve` 3, `no_right_turn` 3, `t_junction_right` 2.
- [ ] End-to-end M1 -> M2 on a held-out clip. Nothing has run the two together
      yet, and the live dash demo is exactly that.
- [ ] Entropic Open-Set loss + OSCR, if M2 survives the presentation.
- [ ] The 15 deleted boxes the model reads as bus-stop/information signs. Decide
      whether a bus-stop board is `information` or `not_a_sign` and be consistent;
      right now it is whatever the reviewer felt that minute.
- [ ] `--synth 2400` and the 0.7-1.0 RandomResizedCrop were guesses that worked
      first time. Nobody has tried a second value.

## 2026-11-16 — A rule for `information`, a full human pass, and a number that was never real

### Qwen is the wrong labeller for this footage, and the mix is why

The note in `note.txt` said autolabel v2 was not efficient for distillation and
the Qwen prompt needed rewriting. The prompt is not the problem.

The golden experiment measured Qwen2.5-VL at 83.5% accuracy / 71.5% macro-recall
(RESULTS.md section 7). Both numbers are carried by one class: that test set is
54% `information` boards and Qwen reads them 201/202. Strip `information` and the
rest scores 67%.

b02-1 has the opposite mix. Its biggest class is `no_stopping_parking` at 144 of
547 boxes — Qwen's **worst** class, 4/23 = 17%. `information` is only 16% here.
Project the measured per-class recalls onto b02-1's actual counts:

```
388 boxes with a measured class  ->  58.4% right,  41.6% wrong
all 547 boxes                    ->  41.4% right,  58.6% wrong
```

Two structural holes on top of the mix. 130 of 547 boxes are things the prompt
never describes — 116 `not_a_sign`, 10 `no_pedestrians`, 2 `mandatory_direction`
— and the prompt opens "This photo is a Thai road sign" with no way out. And 156
of 496 crops never reached the model at all: `qwen_label.py` skips any crop with
no coarse class, and M1 is class-agnostic by design.

The raw b02-1 Qwen output no longer exists to score directly — `review.py`
rewrites `predictions.csv` on every pass, and `.bak` already held CVAT
corrections (`not_a_sign` and `dont_know` are review.py keystrokes, not Qwen
vocabulary). The figures above are a projection built from measured parts, and
they are labelled as such. **Keep the next batch's Colab download untouched** so
the next prompt can be scored instead of estimated.

### `prelabel.py from-m2`

M2 scores 99.1% on `no_stopping_parking` and 88.5% over all 932 val crops. Once
a class has training crops, the classifier is simply the better labeller, and it
runs on the Mac in seconds instead of a Colab round trip. So `from-m2` replaces
`from-colab` in the default path, and `detect` now says so.

Smoke test on b02-1: 486 of 496 crops named in 3 seconds, 90.4% agreement with
the human labels. That batch is in M2's training set, so it says the wiring
works, not how good the model is.

The confidence column rides along. Reviewing only the 15% of boxes below 0.80
catches 54% of the errors.

`from-m2` refuses to run on a batch with a `confirmed.csv` unless forced, because
`predictions.csv` is also where `review.py` stores the human's answers — a
re-run would quietly erase a day of labelling. It fired on the first real test.

Qwen keeps one job: a class M2 has never seen. `keep_right` has zero crops
anywhere, and a classifier cannot name what it was never trained on. That is the
only distillation left.

### The rule

`information` had no written definition, so it was whatever the reviewer felt
that minute, and the model had learned both answers. Of M2's `not_a_sign`
mistakes, 10 went to `information` and 9 to `reserved_for_bus` — over half of
them on one boundary.

> `information` is a guide sign erected by the road authority: place names,
> distances, direction arrows, lane diagrams. Everything else rectangular with
> text on it is not a sign and its box is deleted — shop fronts, billboards,
> posters, bus-stop boards.

It lives in `classes.py` next to the class it governs. An appearance test cannot
settle this, which is why having one was not enough: a billboard really is "a
large board with text", and M2 calls one `information` at 0.94 for exactly that
reason. The test has to be who erected it and whether it helps you drive. It
matters because `information` is one of the 13 the dash SHOWS — label a bus
shelter `information` and the screen speaks at every bus stop.

### `reserved_for_bus` was never the sign it is named after

All 19 crops in that class are bus-stop boards: blue arch, white bus, "BUS STOP"
along the bottom. Not one is the blue regulatory bus-lane sign the name means.
Eight identical boards had been deleted as `not_a_sign` in the same footage.

So M2 naming the deleted ones `reserved_for_bus` at 0.98 was never a model error
— it had learned exactly what it was taught, then was marked wrong for it. This
was written up as "a definition question"; it was an inconsistency, which is a
smaller and more fixable thing.

All 21 boxes are now `not_a_sign`. The class name stays in `classes.py` with zero
crops, like `keep_right`: deleting it would renumber `THAI_FINE_NAMES`, and that
order is frozen. `cmd_build` drops a `not_a_sign` box and keeps the frame, so
M1 learns bus stops are background, while `build_m2` harvests them as reject
crops — M2 does not stop learning them, it learns to refuse them, which is what
you want the moment M1 fires on one anyway.

### A sweep, deleted the same day

`sweep_labels.py` ran M2 over every human label and printed each crop it argued
with. 36 arguments in 1729 boxes, 10 of them real errors — two overhead green
guide boards deleted as not-signs, a real no-parking sign deleted, a height limit
in `other_regulatory`, a chevron in `other_warning`, two `dont_know` crops that
were plainly pedestrian crossings. The score did not move, and 26 of the 36 were
the model being wrong.

A model disagreeing with its own training labels mostly marks where it is
undertrained. 178 lines for that is a bad trade, and it was deleted. What finds
label problems here is rendering a class and looking at it — the wrong turn-sign
artwork, the `no_left_turn` crops that were really no-parking, the bus stops.
None of those came from a filter.

`review.py --only <class>` already does exactly that, one crop at a time, and
writes renames straight back. It did not need a new tool; it needed to be used.

### 45 commands, 82 label corrections

One `review.py <batch> --only <class>` per class per batch, smallest first. The
pass moved 61 labels, and the big one was not subtle: **41 chevrons were still
sitting in `other_warning`** in b01, which dropped 92 -> 47. Plus the 21 bus
boards.

No box was added or deleted, so M1 needed no retraining — it is class-agnostic,
and renaming a box does not change its training data at all.

### `x` was refused, 21 times, silently

The bus-stop pass did nothing. `sync_reviewed` refuses every SPECIAL, including
`not_a_sign`, on the grounds that only CVAT shows the whole frame. It prints a
`!! NOT applied` line that is easy to miss after a long pass.

That guard is about ONE box: you cannot tell from a 128 px crop whether that box
belongs. Under `--only` you are answering a different question — "is this KIND of
thing a sign?" — and the frame adds nothing to it. So `not_a_sign` now lands when
`--only` is set, and nothing else does; `dont_know` still drops a whole frame and
stays refused either way. Both halves are asserted in `review.py selfcheck`.

### Where M2 stands, and which number to quote

Both checkpoints on the same 996 val crops:

| | macro (11 displayed) | quiet | all 996 crops |
|---|---|---|---|
| before the review pass | 87.5% | 95.5% | 876 = **88.0%** |
| after | 87.7% | 94.3% | 899 = **90.3%** |

The macro moved 0.2 points and the whole-dataset number moved 2.3. The label work
is real; the headline metric cannot see it.

| class | n | before | after |
|---|---|---|---|
| `information` | 154 | 96.8% | **100%** |
| `stop` | 10 | 70.0% | 90.0% |
| `no_left_turn` | 13 | 61.5% | 84.6% |
| `right_curve` | 5 | 60.0% | 100% |
| `keep_left` | 5 | 100% | 60.0% |
| `no_right_u_turn` | 5 | 100% | 80.0% |
| `turn_right` | 9 | 100% | 88.9% |

Six of the eleven scored classes have 5–13 val crops, so one crop is 8–20 points.
Every swing above except `information` is one to three crops.

**93.6% was never real.** `train_m2.py` saves the best of 30 epochs, and that run
spiked to 93.6 at epoch 20 with 91 and 86 either side. Both earlier runs plateau
at 88–89. It was quoted several times, including in this journal, and it is
withdrawn: **quote 90.3% over all 996 val crops, and `information` 100% on 154.**
This run's curve is also visibly flatter (last ten epochs span 84.9–87.7 against
86–93.6 before), which is what cleaner labels should look like.

### Open

- [x] Bus-stop boards. Settled: `not_a_sign`, by a written rule.
- [ ] Footage, still: `keep_right` 0 clips, `right_curve` 3, `no_right_turn` 3,
      `t_junction_right` 2. Six displayed classes have 5 or fewer val crops, which
      is what makes the macro unquotable. This is a filming problem.
- [ ] A stable headline. Best-of-30 on a macro over small classes selects a lucky
      epoch. Report the plateau, or score on something bigger than 5 crops.
- [ ] Entropic Open-Set loss + OSCR, if M2 survives the presentation.
- [ ] `--synth 2400` and the 0.7-1.0 RandomResizedCrop are still guesses that
      worked first time. Nobody has tried a second value.

## 2026-11-16 (night) — b02-2 lands: M2 gets better overall and worse at the one class that matters

759 new frames, 1068 crops, reviewed in one sitting. Both models retrained. The
honest summary is that this batch bought a real improvement and charged for it in
the most expensive currency available.

### The dataset now

| | frames | boxes |
|---|---|---|
| b01 | 880 | — |
| b02-1 | 350 | — |
| b02-2 | 759 | — |
| **built** | **1989** (1561 train / 428 val) | 2104 |

M2's crops: 2970 train / 1151 val across 29 classes. **`not_a_sign` is now 1766
of the 2970 training crops — 59% of the dataset.** b02-2's review deleted 653 of
its 1068 boxes, which is what picking at `conf 0.15` is *for*, but it moves the
centre of gravity of what M2 is learning.

### M2: +6.0 all-class, −8.8 on `information`

Both checkpoints scored on the **same 1151 crops**, so for once this is a model
comparison and not a model-and-exam comparison:

| | all 1151 | macro@12 | quiet | `information` (137) | `not_a_sign` (569) |
|---|---|---|---|---|---|
| **new, 3 batches** | **83.7%** | 86.3% | 92.8% | 85.4% | 82.1% |
| prev, 2 batches | 77.7% | 87.3% | 88.9% | 94.2% | 74.5% |

Read it as one trade, not five numbers. The model got **better at rejecting**
(`not_a_sign` 74.5 → 82.1, quiet 88.9 → 92.8) and that is almost all of the +6.0.
It paid for it by rejecting things it should have named: **`information` fell from
129/137 to 117/137, and all twelve losses went to `not_a_sign`.**

That is the rule written into `classes.py` this morning, working, and then
over-working. Billboards, shop fronts and bus-stop boards got deleted in review
exactly as the rule says; `build_m2` harvested them as `not_a_sign` crops; M2
learned the boundary harder. It now shaves real guide signs off the same edge.

The direction is the safe one — the dash goes quiet instead of announcing the
wrong thing — but a missed `information` is still a missed sign, and
`information` is 54% of what this footage contains.

The macro went *down* 1 point while all-class went *up* 6. That is the small-class
macro doing what it always does; ignore it. **Quote 83.7%.**

Note the headline is lower than yesterday's 90.3% and this is not a regression:
the val set grew from 996 to 1151 crops and got harder. Yesterday's checkpoint
scores **77.7%** on today's exam. Comparing 90.3 to 83.7 compares two exams.

### M1: three runs, three different val sets

`m1-floor16-b02-2`, yolo26n, imgsz 1280, `fliplr=0`, batch 8, AdamW lr0 1e-3,
mosaic 0.5. Best epoch 18, early-stopped at 46 on patience 20.

| run | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|
| floor16, b01 | 0.903 | 0.689 | 0.814 | 0.684 |
| floor16, b01+b02-1 | 0.852 | 0.820 | 0.876 | 0.741 |
| floor16, all three | 0.791 | 0.800 | 0.850 | 0.680 |

Every number fell. **Do not read that as a worse model.** `prelabel.py build`
re-splits by clip every time a batch lands, so all three rows were scored on
different val sets — and unlike M2 above, no apples-to-apples rerun was done,
because the old val clips may now be in the new train split and the comparison
would be contaminated in the old model's favour.

So: the M1 column of this table has been unreadable for three runs running. The
fix is to freeze a val set — pick the clips once, never re-split them — and it is
now the most valuable hour available, because it is the difference between having
a trend and having three unrelated numbers.

### Shipped

`central/sign_v3/` updated to both new checkpoints (`m1.pt` `69a75ce304ad`,
`m2.pt` `7efca804bb4f`), README numbers rewritten, `run.py --selfcheck` passes.

### Open

- [ ] **Freeze M1's val split.** Three runs, three exams, no trend. Highest value
      item on this list.
- [ ] `information` vs `not_a_sign` is now the live boundary, not bus stops. Look
      at the 12 losses before adding more `not_a_sign` crops — if they are genuine
      guide signs, the next batch makes this worse, not better.
- [ ] Footage, still: `keep_right` 0 clips, `right_curve` 3, `no_right_turn` 3,
      `t_junction_right` 2.
- [ ] A stable headline. Best-of-N on a small-class macro still selects a lucky
      epoch; all-class on 1151 crops is the number that holds still.
- [ ] Entropic Open-Set loss + OSCR, if M2 survives the presentation.
- [ ] Pi: `run.py` has never been run on the Pi. No CPU timing exists. The AI HAT
      needs an x86 Linux host for the Dataflow Compiler; nothing is blocked on it
      for a demo, only speed.
