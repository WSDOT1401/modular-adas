# JOURNAL — how this pipeline got built, and what we learned the hard way

The [README](README.md) says *how* to run it. [RESULTS.md](RESULTS.md) holds the
measured numbers. This file holds the *why*: the decisions, the things that
broke, and the findings that are only interesting because of what came before
them.

Written as we went. Read it if you are porting the pipeline, reviewing the
method, or wondering why something is built the odd way it is.

---

## Why tracking instead of screenshots

The original dataset sampled a frame every 225 frames (7.5 s) and hand-labelled
it. That gave ~16 signs per clip.

The problem is not labelling effort, it is *blindness*. At 7.5 s spacing you are
blind for about 150 m of road at a time, and every sign that appears and passes
between two screenshots is gone. Worse, the signs you do catch are caught at a
random distance — usually far away and unreadable.

Measured on `2026_0912_013522.MP4` (3 min, 5,400 frames):

| | screenshot every 7.5 s | detector watches everything |
|---|---|---|
| signs found per clip | ~16 | **66** |
| typical crop size | 41 px | **84 px** |
| compute per clip | 0 | ~2.5 min |

**4× more signs, from footage we already had** — not because the detector got
better, but because we stopped throwing away 99% of the video.

That is the entire thesis of the pipeline. Everything else is bookkeeping around
it.

---

## The ordering problem (step 0 needs step 1)

The gold set needs crops, and crops come from tracking. So the real order is:
run tracking on a few clips first, build the answer key from *those* crops, and
only then decide whether the rest of the pipeline is worth building.

We also deliberately did **not** build the gold set from the old hand-annotated
dataset. Those crops are ~41 px; real pipeline crops are ~84 px. Grading a model
on the old ones would have been an unfairly hard test that told us nothing about
how the pipeline would actually perform.

---

## Things the detector gets wrong

Measured on `2026_0912_013522.MP4`, 59 tracks with ≥3 detections.

### The coarse class flips mid-track

The same sign is called `Warning` at second 8 and `Information` at second 12 —
on **8 of 59 tracks (14%)**.

**It does not hurt us**, and understanding why shaped the design. The tracker
keeps it as one sign anyway: the class changes, the ID does not. A human
confirms the class once at the close-up frame, and propagation overwrites every
other sighting with that answer. The flip erases itself.

How often a detection disagrees with its own track's close-up view:

| sign size | disagrees |
|---|---|
| under 30 px | 2.7% |
| 30–60 px | **14.7%** ← the confused zone |
| 60–100 px | 3.6% |
| over 100 px | **0.0%** |

Over 100 px the detector never changed its mind once, in 105 detections. The
close-up frame is a trustworthy judge — it agreed with the whole-track majority
vote 54 times out of 59.

A flip is still a useful **warning light**: those signs confused the detector, so
they belong at the top of the review pile.

### Confidence lies about small signs

| sign size | median confidence |
|---|---|
| under 30 px | **0.78** |
| 30–60 px | 0.90 |
| over 100 px | 0.88 |

A 20 px sign — a grey smudge a human cannot identify — still scores 0.78. The
detector is confidently guessing.

**So we filter by pixel size, not confidence.** `--min-best-side 60` is a real
filter. `if conf > 0.7` would have let hundreds of unreadable signs straight into
the dataset, and we would never have seen it happen.

---

## Two tracking bugs that cost 15% of the gold set

Raw tracker output had **duplicate tracks** — the same physical sign appearing
as two crops, which means two humans labelling the same thing twice and an
answer key that double-counts it. 15% of the gold set, 82% of that inside
`information` (the big overhead boards).

Two distinct causes, needing two different fixes, both now in
`dedup_tracks()`:

* **overlap** — two IDs on one sign in the same frames. Caught by IoU > 0.5 on
  ≥2 shared frames.
* **hand-off** — a track is lost for a few frames and the sign is reborn under a
  new ID. 31 of 543. Caught by position + size continuity across a small frame
  gap.

Merging repeats until nothing changes: merging A and B widens the frame span,
which can make the result a hand-off match for a C that neither half reached
alone. One pass left exactly that case on the real footage.

---

## Measuring the VLM: the metric was wrong before we measured anything

We nearly reported a number that was worse than useless.

`information` is 56% of the answer key, and once a crop's coarse class is known
the Information parent offers only two choices. So a three-line program that
never opens an image — "Information → information, Warning → other_warning,
Regulatory → no_stopping_parking" — scores **76.6% accuracy**.

The README at the time had a grading table whose hoped-for headline was 71%.
That would have been *below a program that cannot see*.

We switched to **macro-recall** over classes with ≥5 examples, where the blind
program scores **33.3%**, and made `classify.py score` print both baselines on
the same line as every number so neither can be quoted alone.

**The lesson generalises:** on any imbalanced dataset, decide what "no better
than guessing" scores *before* you look at a model's result. Otherwise you will
find a way to be impressed by it.

---

## Three prompt iterations, and where the cheating line is

| | v1 | v2 | **v3** | blind |
|---|---|---|---|---|
| macro-recall (9 classes, n≥5) | 61.3% | 69.9% | **71.5%** | 33.3% |
| accuracy | 69.4% | 83.2% | **83.5%** | 76.6% |
| catch-all recall (78 crops) | 5% | 68% | **68%** | — |
| unparseable / abstained | 2 / 1 | 0 / 0 | 0 / 0 | — |

Human ceiling: 91.7% inter-annotator agreement.

**The line we held:** descriptions were written from a contact sheet of three
example crops per class, *before* seeing the error list, and every class was
described to the same level of detail — including the ones already working.
Writing a description for the class that failed, and only that one, is tuning on
the test set.

### Finding 1 — the chevron result

`other_warning` went 4/63 → 46/63.

**The prompt never mentions chevrons.** Describing `right_curve` as "yellow
diamond, a single black arrow bending to the right" was enough for the model to
exclude a chevron board (rectangle, solid arrowhead) *by itself*. We withheld
the hint deliberately, which is what makes this a result rather than a hand-fed
answer.

### Finding 2 — naming the behaviour unlocked the catch-all

v1 used a catch-all 4 times in 376 crops. v2 used one 75 times, 53 of them
correctly.

Listing `other_*` as an option was not enough — v1 already did that. What changed
was one sentence: *"Do not pick the closest match — a sign that merely resembles
an option, without matching its description, is other_X."*

A model will not volunteer "none of the above" unless you tell it that is a real
answer.

### Finding 3 — a score that hides the thing you care about

`no_stopping_parking` went 1/23 → 4/23. Barely moved.

But the *failure mode* inverted: v1 produced 13 confident wrong labels
(`no_left_turn`); v3 routed 16 to `other_regulatory`. Same score, opposite
operational consequence — a wrong label corrupts the dataset silently, a
catch-all lands in the review queue where a human sees it.

**Macro-recall could not see this.** Read the confusion matrix, not just the
headline.

### Finding 4 — a description narrower than its own class (left unfixed)

`u_turn` **regressed**: 7/7 in v1 (no descriptions at all) → 3/7 in v3.

All 4 failures are *yellow diamond* U-turn signs. All 3 successes are blue
squares. Our description said "blue square with a white U-turn arrow" — narrower
than the class it was describing, so the model correctly rejected every yellow
one.

**We left it broken on purpose.** It is only knowable from the score, and fixing
it would be a fourth iteration against the same 376 crops. It is reported as a
limitation instead.

### Determinism

v3's Regulatory and Warning prompts were byte-identical to v2 and reproduced
byte-identical outputs (64/64 and 103/103). Greedy decoding, no sampling — so
every run-to-run delta is attributable to the prompt, not noise.

---

## The bug that nearly invalidated a run

`prompt_for()` built the catch-all as `"other_" + parent.lower()`, which offered
the model `other_information` — **a class `classes.py` does not define**. Then
`parse_answer()`'s substring match found `"information"` inside
`"other_information"` and recorded a confident `information`.

80 of 209 Information crops in v2 went through that path.

Two fixes, both now asserted in `classify.py selfcheck`:

* `catch_all()` reads the real catch-all out of `classes.py` instead of
  constructing a name.
* `parse_answer()` matches on word boundaries (`\b`), not substrings.

**The honest postscript:** we predicted v3's Information score would fall. Only
one crop changed. `information` genuinely *is* Information's catch-all, so the
bad substring match happened to land on the correct label — the results were
right by luck. The fixes still matter: the same parser would have matched
`keep_left` inside `keep_left_or_right`.

Lucky-correct is not correct. But do not overstate it either — we briefly called
v2's Information numbers "void" and that was wrong.

---

## Where the human-in-the-loop step was missing

For most of the build there were two human steps in the diagram and **only one
tool**, and it did blind labelling. There was no way for a human to *review* a
model's answer — which is the entire point of a pre-annotation pipeline.

So the pipeline, as built, measured that a VLM *could* save work without ever
actually saving any.

The fix was smaller than expected: `sort.py` already moved a crop into the
folder you clicked. Review mode just pre-selects the model's answer and binds
Enter to it. The same tool does both passes, and which mode it is in depends
only on whether `predictions.csv` exists.

It also writes `review_log.csv`, so the **accept rate is measured rather than
estimated**. That number — not the offline macro-recall — is the one that
translates into hours not spent, because it is measured on crops a human
actually had to get through.

---

## The gold workspace is a filtered view, and propagate.py did not know

Asked why `--skip-done` points at `work/gold/tracks.json`, the answer is dull —
it is the union of every pass, so it is the only file that knows all 35 clips.
Checking it turned up something that was not dull.

```
pass1 + pass2:  886 tracks
work/gold:      458 tracks   <- only the ones a human could name
```

`gold.py add` drops tracks whose closest view is under `--min-best-side 60`.
Correct: there is nothing to label on a 27px smudge. But `propagate.py` read
only the gold workspace, so **428 real signs were invisible to it** — and a
frame is one training image:

```
frames going into the dataset that contain an UNLABELLED real sign: 413 of 2291 (18%)
their size: median 27px, p90 46px, max 59px
```

YOLO reads empty space as a correct answer. 18% of the dataset was teaching the
detector that distant signs are background — the exact opposite of the claim the
whole pipeline rests on, that tracking buys correct labels for signs at a
distance.

**The fix** has `propagate.py` read `work/pass*/tracks.json` as well, and drop
frames holding an unnameable sign at or above `--tolerate-under` (default 30px).

The threshold comes from the detector-behaviour table above: below 30px it
disagrees with its own track 2.7% of the time because it is barely registering
the sign at all; in the 30-60px band that jumps to 14.7% — clearly seen, not
nameable. Those are the ones where the lie costs something.

| `--tolerate-under` | boxes | vs. broken |
|---|---|---|
| 0 (drop every affected frame) | 1,997 | -18.7% |
| **30 (default)** | **2,254** | **-8.2%** |
| 999 (the old behaviour) | 2,456 | — |

The headline number went 2,456 → **2,254 boxes on 2,107 frames**, still from 376
signs. Worth reporting the corrected figure rather than the inflated one.

**The generalisable bit:** a file that is correct for one job is not therefore
correct for the next one. `tracks.json` in the gold workspace is a *labelling*
queue, and reusing it as a *dataset* manifest silently inherited its filter.
`--report` now warns loudly when it cannot find the pass dirs, because the
failure is otherwise invisible — you just get a slightly worse model.

---

## The same bug twice: a frame is a picture, not a row

`propagate.py` had it (signs too far to name, sitting unboxed in a training
image). Then `cvat.py export` turned out to have it too, in a different costume.

Export grouped boxes by each track's **peak frame** and drew only the track that
peaked there. But a frame is a whole picture: other signs are standing in it at
non-peak moments, and they got no box. Measured on pass3:

```
40 of 104 exported frames (38%) showed a sign with no box
  36 of those signs were labelable -- already in the task, on their own frame
  10 were sub-threshold -- never reviewed anywhere
```

For a human reviewer this is worse than for a model. They see an obvious 222px
sign with no box, assume the tool missed it, and draw it by hand -- work that
`import` then discards, because an added box has no track to propagate along.

Fixed by drawing every track visible on an exported frame. `import` then has to
match and *consume* those context boxes before counting leftovers, or each one
would register as a sign the reviewers added and fake a false-negative rate.

**The pattern worth remembering:** both bugs came from treating a frame as a row
in a table (one track, one record) when it is really a picture (everything
visible in it is part of the label). Any time a frame is reused as a unit of
output, ask what else is standing in it.

---

## Scoping decisions worth remembering

**`test_autolabel.py` was deleted, not fixed.** It tested five `track.py`
functions that no longer existed and failed 5/5. A test suite that cannot run is
worse than none — it reads as a passing check to anyone who does not run it.
Replaced with `--selfcheck` subcommands that assert the maths and the two
parsing bugs that cost us a run.

**`crops.py` and `cvat.py` were never built.** The README described them for
weeks. `track.py` already writes crops and a CVAT-importable task, so both were
pure duplication. Deleting them from the docs was the fix.

**`--solo` was added after a wrong claim.** We told the user new footage could be
labelled alone, then read `gold.py cmd_score` and found `set(la) & set(lb)` —
single-annotator crops could never reach the answer key. `--solo` keys them,
marked `annotators=1`, with the agreement rate still computed on two-annotator
crops alone.

---

## Open questions

* **Crops #2, #21, #23** may have been swept into `not_a_sign` during settlement.
  Worth re-checking.
* **`stop` has one distinct sign in 35 clips.** `propagate.py --min-signs 5`
  folds it into `other_regulatory` — which means the dataset currently *cannot*
  demonstrate the one requirement the project exists for. This is a filming
  problem, not an engineering one.
* **Four clips in the old dataset have no footage file** (`2025_1230_004245`,
  `20260908_184333_REC_F`, `20260909_115404_REC_F`, `20260909_115504_REC_F`).
* **Propagated boxes are never re-detected.** If the tracker drifted, the drift
  is in the labels. Nobody has measured how often that happens.
