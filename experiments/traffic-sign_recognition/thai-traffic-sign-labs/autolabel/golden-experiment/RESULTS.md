# Gold set — measured results

Step 0 of the autolabel pipeline (see `README.md`). All figures measured
**2026-10-04** from `work/gold/`. Regenerate with `python gold.py score`;
the detector table is reproduced at the bottom of this file.

`work/` is gitignored, so this file is the durable record. If a number here
disagrees with something said in a chat log, trust this file.

---

## 1. Inputs

| | |
|---|---|
| Footage | 35 clips · 63 min · 9.9 GB dashcam, Thailand |
| Clips used | **35 of 35** — the gold set is the entire harvest, not a sample |
| Detector | `best.pt`, 3 coarse classes (Regulatory / Warning / Information) |
| Tracking | ByteTrack, `imgsz=1280`, `conf=0.15`, `vid_stride=3` |

## 2. Pipeline yield

One crop per *distinct sign*: tracked across frames, keep the frame where the
sign is largest, then merge tracks that are the same physical sign.

| | |
|---|---|
| Crops after dedup + the 60 px floor | **458** |
| Detections per track | median 34 |
| Sign size at peak frame | median **136 px**; p10 70 · p90 470 · max 1004 |
| Coarse class flips mid-track | 25 / 458 = **5%** (14 / 332 = 4% on signs ≥100 px) |

Flips are harmless here: only the peak frame's class is kept, and the peak frame
is the largest and clearest view.

## 3. Inter-annotator agreement — the headline number

Two labellers, independently, blind to each other's answers. 458 crops each,
21 fine classes plus 4 dispositions.

> ### **420 / 458 = 91.7% agreement**
>
> This is the human ceiling. No model score on this set is meaningful without
> it: 87% against a 91.7% ceiling is a strong result, not a mediocre one.

**Quote 91.7%, not the 100% that `gold.py score` prints now.** The post-
settlement number is arithmetic — the disagreements were resolved *into* the
key — and reporting it would be wrong.

### What the 38 disagreements were

| count | disagreement |
|---|---|
| **30 (79%)** | one labeller said `not_a_sign`, the other named a class |
| 5 | `dont_know` vs a named class |
| 3 | genuine fine-class confusion |

The split is the finding: **almost none of the human disagreement was about
fine-grained classification.** It was about whether the thing in the box was a
traffic sign at all — Thai text-only warning boards, motorway guide boards, and
shop frontage. Fine-grained labelling, once both people agree something *is* a
sign, is close to unambiguous.

Two class-definition rules were written during settlement and are now binding:

- **A.** It is a road sign if the road authority put it there for drivers.
  Place names, route numbers, school boards → `information`. Shop names, brand
  adverts, property boards, building exits → `not_a_sign`.
- **B.** A Thai text-only yellow or green board *is* a warning sign. No triangle
  or diamond required.

## 4. The answer key

```
378 crops      excluded: 78 not_a_sign (17%) · 2 composite
```

| class | n | | class | n |
|---|---:|---|---|---:|
| information | **202** | | left_curve | 7 |
| other_warning | **63** | | t_junction_left | 3 |
| pedestrian_crossing | 27 | | no_right_u_turn · right_curve · turn_right | 2 |
| no_stopping_parking | 23 | | too_small | 2 |
| other_regulatory | 15 | | stop · no_left_turn · no_right_turn | 1 |
| speed_limit | 9 | | turn_left · reserved_for_bus · t_junction_right | 1 |
| keep_left_or_right | 8 | | **keep_left · keep_right** | **0** |
| u_turn | 7 | | | |

`composite` is a disposition, not a class: the box holds a sign *assembly*
rather than a sign — a school-zone banner containing both a pedestrian diamond
and a 30 roundel. Labelling it `speed_limit` would teach "orange banner = speed
limit"; labelling it `not_a_sign` would teach the opposite. Both are wrong, so
it is excluded and counted. The fix is to split the box at step 2.

## 5. Detector (`best.pt`) performance

Coarse prediction vs. the human fine label's parent class:

```
detector says     Regulatory  Warning  Information  not_a_sign  too_small  composite   total  correct
Regulatory                53        0            3          10          0          0      66      80%
Warning                    9       88            4           2          0          1     104      85%
Information                2       15          202          66          2          1     288      70%
```

| | |
|---|---|
| Coarse accuracy on real signs | **343 / 376 = 91.2%** |
| False positive rate | **78 / 458 = 17%** |

`Information` carries nearly all the error: 66 of its 288 detections were not
signs at all. Thai motorway guide boards are large, rectangular, high-contrast
and text-filled — and so are billboards and shop frontage. This is the
detector's weakest boundary and it is the same boundary the humans argued over
in §3.

---

## 6. Baselines any model must beat

Measured from `answer_key.csv` itself, 2026-10-04. These do not depend on any
model, so they are fixed until the answer key changes.

A program that **never opens the image** and answers with its parent's commonest
class — "Information → information, Warning → other_warning, Regulatory →
no_stopping_parking":

| parent | n | blind answer | gets |
|---|---|---|---|
| Regulatory | 64 | `no_stopping_parking` | 23/64 = 36% |
| Warning | 103 | `other_warning` | 63/103 = 61% |
| Information | 209 | `information` | 202/209 = 97% |
| **overall accuracy** | **376** | | **288/376 = 76.6%** |

So **76.6% accuracy is the floor, not a result.** `information` alone is 56% of
the key, and the Information parent offers only two choices once the coarse
class is known.

The metric that discriminates is **macro-recall** — per-class recall averaged
with every class weighted equally, over the 9 classes with ≥5 examples
(`no_stopping_parking` 23, `other_regulatory` 15, `speed_limit` 9,
`keep_left_or_right` 8, `pedestrian_crossing` 27, `other_warning` 63,
`left_curve` 7, `information` 202, `u_turn` 7). The blind program scores
**3/9 = 33.3%** there.

Verified by scoring a simulated blind predictor through `classify.py score`; it
reproduces 76.6% / 33.3% exactly.

The other 10 present classes have 1–3 examples each and are excluded from the
average — `stop` has exactly **one** crop. Report those as found/missed, never
as a percentage.

**Quote macro-recall. If you quote accuracy, print 76.6% beside it.**

## 7. VLM baseline — Qwen2.5-VL-7B, 2026-10-04

`Qwen/Qwen2.5-VL-7B-Instruct`, 4-bit NF4 / fp16 compute on a free Colab T4,
greedy decoding, one sample. Tight crops, resolution floored at 448² so nothing
was downscaled. Coarse class supplied from the human label, so the model chose
among at most 13 names, never 21.

**Three runs. Quote v3.**

| metric | v1 | v2 | **v3** | blind baseline |
|---|---|---|---|---|
| **macro-recall** (9 classes, n≥5) | 61.3% | 69.9% | **71.5%** | 33.3% |
| accuracy | 69.4% | 83.2% | **83.5%** | 76.6% |
| catch-all recall (78 crops) | 5% | 68% | **68%** | — |
| unparseable / abstained | 2 / 1 | 0 / 0 | **0 / 0** | — |

v1 scored *below* the blind baseline on accuracy while scoring nearly double on
macro-recall — the clearest demonstration of why this set cannot be graded on
accuracy. v2 and v3 clear both.

### What changed between runs

**v1 → v2 (prompt).** v1 gave the model bare `snake_case` names and nothing
else, while the human annotators had the `classes.py` comments and the two
definitions they wrote during settlement — an unfair comparison, not a model
limitation. v2 added a one-line visual description to every class and a closing
rule:

> *Rule: if the sign does not match one of the descriptions above, answer
> `other_warning`. Do not pick the closest match — a sign that merely resembles
> an option, without matching its description, is `other_warning`.*

Descriptions were written from a contact sheet of three example crops per class,
**not** from v1's error list. Two contradicted European convention and would have
been wrong from memory: `keep_left_or_right` is a yellow diamond here (not a blue
circle), and `turn_left`/`turn_right` are red-ringed white circles (not blue).

**v2 → v3 (two bug fixes, no description changed).**

1. `prompt_for` built the catch-all as `"other_" + parent.lower()`, so the
   Information prompt offered `other_information` — a class `classes.py` does not
   define. 80 of 209 Information crops came back as it. v3 derives the catch-all
   from `classes.py` (`information` itself, which that file documents as the
   catch-all).
2. `parse_answer` matched substrings, and `"information" in "other_information"`
   is `True`, so those 80 refusals were recorded as confident `information`
   answers. v3 matches on word boundaries, which also stops `keep_left` matching
   inside `keep_left_or_right` and `no_right_turn` inside `no_right_u_turn` — two
   latent mis-parses that had not yet fired. Both halves are asserted in
   `classify.py selfcheck`.

**The outcome of bug 1+2 was benign**, which was not predicted: only **one crop**
changed between v2 and v3. `information` really is Information's catch-all, so the
bad substring match happened to land on the correct label. The bugs were real and
the fixes are permanent, but v2's Information figures were right by luck, not
wrong.

### Determinism check

v3's Regulatory and Warning prompts are **byte-identical** to v2's. Their outputs
reproduced **64/64 and 103/103**. Greedy decoding on this stack is deterministic,
so every difference between runs is attributable to the prompt and none of it to
sampling noise. (This is why only Information moved.)

### Per class

| class | n | v1 | v2 | v3 |
|---|---|---|---|---|
| `other_warning` | 63 | 4 | 46 | **46** |
| `other_regulatory` | 15 | 0 | 7 | **7** |
| `no_stopping_parking` | 23 | 1 | 4 | **4** |
| `information` | 202 | 198 | 201 | **201** |
| `keep_left_or_right` | 8 | 6 | 8 | **8** |
| `speed_limit` | 9 | 9 | 9 | **9** |
| `left_curve` | 7 | 5 | 5 | **5** |
| `pedestrian_crossing` | 27 | 26 | 25 | **25** |
| `u_turn` | 7 | **7** | 2 | **3** |
| `stop` | 1 | 0 | 1 | **1** |
| `t_junction_left` | 3 | 1 | 2 | **2** |
| `right_curve` | 2 | 2 | 2 | **2** |
| `no_right_u_turn` | 2 | 1 | 0 | **0** |

### Finding 1 — the chevron result

`other_warning` went 4/63 → 46/63. 45 of its 63 crops are chevron boards (yellow
rectangle, one solid black arrowhead), which v1 called `right_curve`.

**The prompt never mentions chevrons.** The fix was describing `right_curve`
accurately — *"yellow diamond, a single black arrow bending to the right"* — which
a chevron does not match, plus the rule against picking the closest match. The
model derived the exclusion itself from a correct class definition.

That is a stronger claim than "we told it the answer", and it is only available
because the chevron hint was withheld deliberately, before the run.

### Finding 2 — naming the behaviour unlocked the catch-all

v1 used a catch-all **4 times** in 376 crops; v2/v3 used one **75 times**, 53
correct. Listing the option was not enough. The sentence "do not pick the closest
match" was.

This matters more than the score: `other_*` is the bucket that routes an unknown
sign to a human. A model that refuses to use it mislabels every unlisted sign
confidently and silently.

### Finding 3 — `no_stopping_parking` improved in a way the score hides

Recall barely moved (1/23 → 4/23 = 17%), but the failure changed character:

- v1: **13 confident wrong labels** (`no_left_turn`) that would enter the dataset
  unnoticed
- v3: **16 routed to `other_regulatory`**, i.e. flagged for a human

Nearly the same score, opposite operational consequence. Qwen still cannot read
the second-largest Regulatory class, but it now knows that it cannot.

### Finding 4 — a description narrower than its class costs recall

`u_turn` fell 7/7 (v1, no descriptions) to 3/7 (v3). The four failures are the
**yellow diamond** U-turn signs; the three that work are blue squares. The
description we wrote says *"blue square with a white U-turn arrow"*, so the model
rejected the diamonds correctly — against a definition that did not cover its own
class.

Descriptions raised macro-recall by ~10 points overall, but a description that is
narrower than the visual variety of its class actively hurts. This is an
annotation-guideline failure, not a model failure, and a human annotator handed
the same guideline would have made the same call.

Deliberately **not fixed**. We only know the description is too narrow because we
read the v3 score; widening it and re-running would be a fourth iteration tuned
against the same 376 crops. Reported instead.

### The one `stop` sign

v1 missed it (`no_left_turn`); v2 and v3 **found it**. One crop is 100% of a
one-example class — an anecdote, not a measurement. The professor's requirement is
met by filming more STOP signs, not by this.

### Methodology — read before quoting

Quote **v3 macro-recall, 71.5%**, and state: three runs, one prompt revision
(v1→v2, all 19 observed classes described uniformly, decided in a single pass) and
one bug-fix revision (v2→v3, no description changed). Report v1 alongside it.

Reproduce:

```bash
python classify.py score --pred work/vlm_run/work/predictions.csv      # v1
python classify.py score --pred work/vlm_run/work/predictions_v2.csv   # v2
python classify.py score --pred work/vlm_run/work/predictions_v3.csv   # v3
```

## 8. Limitations — state these before an examiner finds them

1. **63 minutes of footage is the binding constraint.** Every clip is already
   processed; 458 crops is the complete harvest. Rare classes cannot be fixed
   by more pipeline work, only by more driving.
2. **`stop` has exactly 1 example**, and `keep_left` / `keep_right` have none.
   Eight classes have ≤3. A single example cannot be split into train and
   validation, so per-class results for these are not reportable. Thailand uses
   few STOP signs — most junctions are signalised or yield-controlled — so this
   reflects the road network, not the collection method.
3. **`information` is 53% of the answer key.** Overall accuracy on this set is
   dominated by one easy, visually distinctive class. **Report macro-average
   (mean of per-class accuracy) alongside overall accuracy**, or the headline
   number mostly measures performance on motorway guide boards.
4. **`other_warning` (63) is not one class.** A visual pass puts roughly 45 of
   the 63 as chevron/curve-delineator boards — which would make `chevron` the
   second-largest class in the set. It has not been split out. Until it is,
   `other_warning` accuracy means little. *(Count is an eyeball estimate from a
   contact sheet, not a labelled figure.)*
5. **Day/night is not balanced** and has not been quantified for this crop set.
6. Two labellers only, so 91.7% is an agreement rate, not a kappa; with 21
   classes and this distribution, chance agreement is low enough that the gap
   is small, but it is not zero.

---

## Reproducing the detector table

```bash
conda activate w124-dash-env
python gold.py score                 # §3, §4
python - <<'PY'                      # §5
import csv, collections, sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd().parents[1])); import classes
src = {r['crop_id']: r['coarse'] for r in csv.DictReader(open('work/gold/source_map.csv'))}
human = {f.stem: d.name for d in pathlib.Path('work/gold/labels/rachata').iterdir()
         if d.is_dir() for f in d.glob('*.jpg')}
special = ('not_a_sign', 'too_small', 'composite')
tab = collections.Counter((src.get(c, '?'), h if h in special else classes.THAI_FINE_PARENT.get(h, '?'))
                          for c, h in human.items())
for c in ('Regulatory', 'Warning', 'Information'):
    print(c, {k: v for (p, k), v in tab.items() if p == c})
PY
```
