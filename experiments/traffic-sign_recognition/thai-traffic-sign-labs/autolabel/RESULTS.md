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

## 7. Limitations — state these before an examiner finds them

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
