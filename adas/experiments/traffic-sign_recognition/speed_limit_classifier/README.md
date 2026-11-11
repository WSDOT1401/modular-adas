# Speed-limit digit classifier

Second stage of the sign pipeline. The b01 YOLO detector finds a `speed_limit` sign;
this reads the number inside it.

**Why two stages, not 8 YOLO classes.** The detector runs on frames downsampled to
1280px, where a distant sign's digits are a few pixels tall and unreadable. This stage
gets a dedicated crop at native resolution. Splitting `speed_limit` into
`speed_limit_30/40/...` inside YOLO would instead divide 57 boxes across 9 classes.

## Result

Trained on **synthetic signs only** — it has never seen a real crop during training.

| | |
|---|---|
| Real dashcam crops ≥32px | **33/38 = 86.8%**   95% CI [72.7%, 94.2%] |
| Held-out synthetic | 94.5% |
| Through `classify.py` (with the confidence gate) | 29/38 = 76.3% (answers 31, declines 7) |
| Junk / illegible crops correctly declined | 5/7 (4 by the 32px gate, 1 by confidence) |
| CPU inference | ~74 ms per crop |

Per class: `20` 1/1 · `30` 5/8 · `40` 8/8 · `45` 3/3 · `50` 3/3 · `60` 3/4 · `80` 6/7 ·
`90` 1/1 · `120` 3/3. **`30` is the one weak class.**

> Read the confidence interval, not the headline. With 38 test crops one image is
> 2.6%, so anything under ~10% apart is indistinguishable here. More real test data is
> the binding constraint on this project, not model architecture.

The set was 36 crops at 88.9% until a `review.py` pass resolved two 45px `?` crops to
`60`. The model reads one of them and misreads the other as `120`, so the headline fell
by one crop. The two numbers are the same measurement; do not report the drop as a
regression. The checkpoint was also selected on the 36-crop version of this set, so
86.8% is the fairer figure.

## Files

| | |
|---|---|
| `crops.py` | one-shot: YOLO dataset → `real/` + `labels.csv` + `sheet.png`. Refuses to overwrite hand-read labels. |
| `labels.csv` | the test set, labelled by eye off `sheet.png`. `x` = not a speed limit, `?` = illegible. |
| `synth.py` | draws signs and degrades them into dashcam mush. `python synth.py` writes `synth_sheet.png` — **compare it against `sheet.png`; if they don't look like siblings, nothing downstream works.** |
| `train.py` | fine-tunes MobileNetV3-Small. `python train.py --size 128` |
| `classify.py` | ships to the Pi. `python classify.py` self-checks against `real/`. |
| `review.py` | `python review.py` → http://localhost:8765 to re-check `labels.csv` by eye. Crops grouped by label, Save rewrites the file (old copy → `labels.csv.bak`). |

`sheet.png` and `synth_sheet.png` are generated and not committed. `synth.py`
rebuilds its own; `crops.py` needs `autolabel/dataset/`, which is gitignored.

```python
from classify import SpeedClassifier, SignVote
clf, vote = SpeedClassifier(), SignVote()
for frame, boxes in stream:
    for box in boxes:                  # boxes the detector called speed_limit
        value, conf = clf(frame, box)
        if (settled := vote.update(value)):
            announce(settled)          # fires once per physical sign
```

## Why the data is synthetic

The dataset holds 57 `speed_limit` boxes but only **~28 unique physical signs** — one
video alone contributes 17 frames of the same sign. Three values (`20`, `90`, `60`)
have one or two examples. You cannot fit 2.5M parameters to that, so the real crops are
held back entirely for test and the training set is generated.

A speed-limit sign is a *drawn standard*, so this works: render unlimited clean signs,
then degrade them (perspective, light, downscale, blur, motion smear, JPEG) until they
match the footage. Backgrounds are random tiles from our own frames — in-domain and
already on disk.

## Decisions worth knowing, and what they cost

**Input size 128px, not 64.** This was the single biggest win: **72.2% → 91.7%**.
Not about pixel count — MobileNetV3-Small downsamples **32×**, so 64px input leaves a
**2×2** final feature map with nowhere to encode whether a loop closes at the bottom
(`6` vs `8`). 128px gives 4×4 and costs 13 ms. Before the change `60` scored 0/2 and
`90` 0/1; after, both were perfect. Picking 64px because "the crops are only 39px wide"
optimises the wrong quantity.

**Gate at ≥32px.** Below that a human cannot read the sign either (see `sheet.png`).
Announce "speed limit" without a number rather than guessing.

**`CONF_MIN = 0.60`**, measured: keeps 31/33 correct while dropping 1 of 3 wrong. The
separation is weak — one junk crop scored 0.92 — so it is a mild filter, not a
guarantee. `SignVote` is the real defence.

**Full fine-tune, not a frozen backbone.** Freezing `features` is for when you have a
few hundred real images and nothing else. With a generator there is no shortage of data.

## Bugs that cost real accuracy, all found by looking at images

1. **Digits overflowed the red ring.** `_fit()` sized text by height only, so "120"
   rendered 234px wide inside a 172px field. The model learned "wide dark blob = 3
   digits" and read blurry 2-digit signs as 110/120.
2. **Yellow signs are not yellow signs.** The yellow/orange is a rectangular *backing
   board* behind an ordinary white sign (`real/025.png`), not a coloured sign face.
3. **Sign faces were tinted blue and purple.** `tuple(int(c * rng.uniform(.72,1)) for c
   in colour)` calls `uniform` **once per channel**.
4. **`global SIZE` never reached the DataLoader.** Workers `spawn` on macOS and
   re-import the module, so they kept the default. Trained at 64px, tested at 128px,
   scored 25%. The tell: loss values byte-identical to the previous run.

The pattern: when synthetic data underperforms, render it and look at it. No metric
would have revealed 2 or 3.

## Known limits

- `70`, `100`, `110` are generated and predictable but **have zero real test examples**.
- `30` is weak (5/8) and is the obvious next target.
- `023.png` and `024.png` (both 45px, labelled `60`) are at the edge of what a human
  can read, and no closer frame of either sign exists in the dataset — both are the
  last dumped frame before the car passes the sign. If either reading is wrong the
  headline moves by 2.6%.
- `SignVote` is measured at 20/22 signs, but only 8 signs appear in more than one frame
  here because the dataset is sparsely sampled. In the car you get ~10–30 looks per sign,
  so this underestimates it.
- Training still generates samples below the 32px gate, which adds label noise on inputs
  the system will never be asked about.
- No "not a speed limit" reject class; `CONF_MIN` stands in for it.
- Deployment is plain PyTorch. ONNX later if the Pi needs it.

## Dataset corrections — NOT version-controlled

While reading `sheet.png` three boxes turned out not to be speed limits. They were
fixed in `autolabel/dataset/labels/`, but **that directory is gitignored**, so a
re-export from CVAT silently loses these. Reapply them if you rebuild the dataset:

| Label file | Box (width, normalised) | Action | Why |
|---|---|---|---|
| `train/2025_1230_004245_f003375.txt` | `0.029688` | class `5` → `12` (`other_regulatory`) | height-clearance "5.0 ม" sign |
| `train/2026_0912_020429_f004500.txt` | `0.028863` | delete the line | no sign in the box at all |
| `train/NO20260928-155153-018090F_f001260.txt` | `0.015508` | delete the line | barrier marker on an expressway ramp, car doing 57 km/h |

Match on the **box width**, not the line number — these files hold more than one box.
After the third fix that label file is empty, which YOLO correctly reads as a
background image. This takes `speed_limit` from 60 boxes to 57, and the detector only
benefits after a retrain.
