# central — the two models that ship

Everything else under `experiments/` is how these were *made*. This folder is
what you copy to the Pi.

| file | what it does | size | sha256 |
|---|---|---|---|
| `b01.pt` | finds signs in a frame and names the class (21 Thai classes) | 5.6 MB | `089efd7043d6` |
| `speed_reader.pt` | reads the number off a `speed_limit` crop | 6.3 MB | `e7fd7d1c5d73` |

They run as **two stages**, not one model: the detector works on a frame
downsampled to 1280px, where a distant sign's digits are a few pixels tall and
unreadable. The reader gets its own crop at native resolution.

```
frame ──► b01 ──► boxes ──┬─► class != speed_limit → announce the class
                          └─► class == speed_limit → crop → speed_reader → "70"
```

## Use them

```python
from ultralytics import YOLO
import sys; sys.path.insert(0, ".../speed_limit_classifier")   # for classify.py
from classify import SpeedClassifier, SignVote

det  = YOLO("central/b01.pt")
read = SpeedClassifier(ckpt="central/speed_reader.pt")
vote = SignVote()

for r in det.predict(source=0, stream=True, imgsz=1280, conf=0.5, device="mps"):
    value = None
    for cls, box in zip(r.boxes.cls.tolist(), r.boxes.xyxy.tolist()):
        if r.names[int(cls)] == "speed_limit":
            value, conf = read(r.orig_img, box)       # value is None when it declines
    if (settled := vote.update(value)):               # once per FRAME, not per box
        print("speed limit", settled)
```

`speed_reader.pt` is weights only — the crop geometry and the two gates live in
`adas/experiments/traffic-sign_recognition/speed_limit_classifier/classify.py`. That
file is not duplicated here on purpose; one copy, no drift. Copying to the Pi
means both `.pt`s **and** `classify.py`.

## b01 — the detector

yolo26n fine-tuned on 880 hand-reviewed dashcam frames (695 train / 185 val),
50 epochs at 1280px. Best epoch 32.

| mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|
| 0.439 | 0.350 | 0.600 | 0.338 |

Read that recall honestly: **it misses about two signs in three on a single
frame.** That is survivable only because a sign appears in 10–30 consecutive
frames as you approach it, so the chance of missing it in *every* frame is
small. It is not survivable if you ever judge the system on one still.

The class list is baked into the weights (`r.names`), so there is no mapping
file to keep in sync. `speed_limit` is index 5. The tail classes are thin —
`stop` has 2 boxes in the whole dataset, `no_left_turn` 3 — so anything outside
the top five classes is a guess with a confident-looking number on it.

## speed_reader — the digits

MobileNetV3-Small at 128px input, trained on **synthetic signs only**. It has
never seen a real crop during training; all 60 real crops are the test set.

| real crops ≥32px | through the gates | CPU |
|---|---|---|
| 33/38 = 86.8%, CI [72.7%, 94.2%] | 29/38 = 76.3% (answers 31, declines 7) | ~74 ms |

Two gates, both measured, both already applied inside `SpeedClassifier`:

- **`GATE_PX = 32`** — a box narrower than this is mush to a human too. Returns
  `None`: announce "speed limit" with no number rather than guessing.
- **`CONF_MIN = 0.60`** — mild filter, not a guarantee (one junk crop scored
  0.92). `SignVote` is the real defence.

`30` is the weak class (5/8). `70`, `100`, `110` have zero real test examples.

## Four things that will cost you an afternoon

1. **`imgsz=1280`.** b01 was trained there. At the ultralytics default 640 the
   small signs simply stop existing.
2. **`SignVote.update()` once per frame**, and pass `None` on frames with no
   speed-limit box — that is what rearms it for the next sign. Call it per box
   and it fires once and never again.
3. **Don't crop the box yourself.** `read(frame, box)` squares it up and adds
   the same 10% margin the training crops had. A tight or stretched crop quietly
   drops several points.
4. **`device="mps"`** on the Mac: 31 fps vs 4.4 on CPU at 1280. The reader stays
   on CPU — it only fires on a detection, so the 74 ms is paid a few times a
   minute, not 30 times a second.

## Refreshing these files

They are copies. The originals stay with their training runs:

```bash
cp ../traffic-sign_recognition/thai-traffic-sign-labs/autolabel/results/b01/weights/best.pt b01.pt
cp ../traffic-sign_recognition/speed_limit_classifier/speed_classifier.pt speed_reader.pt
shasum -a 256 *.pt          # compare against the table above
```

`.pt` is gitignored repo-wide, so **these two files are not in version
control** — a fresh clone gets this README and no weights. Retrain or copy them
across by hand.
