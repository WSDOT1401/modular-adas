# sign_v3 — M1 finds the sign, M2 names it

The v3 traffic-sign stack, packaged for the Pi. Everything under
`experiments/traffic-sign_recognition/` is how these were *made*; this folder is
what you copy across.

Two models, deliberately. **M1 is class-agnostic** — it answers "is there a sign
here", not "which sign". **M2 answers "which"**, on a 128px crop, with a reject
class. Splitting them is why either one can be retrained without touching the
other, and why renaming a class costs nothing on the detector side.

```
frame ──► M1 (yolo26n @1280) ──► boxes ──► square 128px crop ──► M2 ──┬─► one of 13 → the dash speaks
                                           (short side ≥ 24px)        └─► one of 16 → the dash stays quiet
```

| file | what | size | sha256 |
|---|---|---|---|
| `m1.pt` | class-agnostic sign detector, yolo26n @1280 | 5.3 MB | `69a75ce304ad` |
| `m2.pt` | 29-class crop classifier, MobileNetV3-Small @128 | 6.0 MB | `7efca804bb4f` |
| `run.py` | both of them, over a clip or a camera | 7 KB | — |

Both `.pt` files **are in git** (`adas/.gitignore` carries a negation for
`central/**/*.pt`). A plain `git clone` gets you a working directory — no LFS, no
hand-copying weights. That is the whole point of `central/`.

## Run it

```bash
pip install ultralytics torch torchvision opencv-python pillow
python run.py ../test-clip.mp4
python run.py ../test-clip.mp4 --seconds 20 --out annotated.mp4
python run.py 0 --stride 1
python run.py --selfcheck
```

`run.py` is self-contained on purpose: no import from the lab tree, no
`classes.py`. The class list, the 13 the dash shows, and the crop size all live
inside `m2.pt`, so there is no mapping file to drift.

It prints the two numbers that matter on a Pi — ms per frame per stage, and what
the dash *would have said*:

```
500 frames, 360 boxes (10 under 24px, dropped)
  M1  101.0 ms/frame
  M2   26.0 ms/frame
  end to end 7.9 fps on the frames it ran

what the dash would have said (7 times):
      4  stop
      2  information
      1  speed_limit
```

That run is the **Mac on MPS**, 1920×1080 at `--stride 2`. It is the baseline to
beat, not a target — see the AI HAT section.

## The two rules that break silently

`run.py` carries its own copy of both, because this folder has to work without
the lab tree:

1. **`imgsz=1280`.** M1 was trained there. At the ultralytics default 640 the
   small signs stop existing — not "score worse", stop being detected.
2. **`READABLE = 24` and `square()`.** Nothing under 24 source px on the short
   side reaches M2, and the crop is squared around the box centre before resize.
   M2's synthetic training data is composited on a square canvas; feed it a
   stretched rectangle and it still answers, just worse. No error, no warning.

`python run.py --selfcheck` asserts both against the originals in
`thai-traffic-sign-v3/build_m2.py` — in this repo, where that tree exists. On the
Pi it says so and skips. Run it on the Mac after any change to either model.

## What these score

**M1** — `m1-floor16-b02-2`, yolo26n, imgsz 1280, `fliplr=0`, best epoch 18 of 46
(early-stopped at patience 20), trained on all three batches:

| P | R | mAP50 | mAP50-95 |
|---|---|---|---|
| 0.791 | **0.800** | 0.850 | 0.680 |

Read the recall honestly: **it misses about 1 sign in 5 on a single frame.**
Survivable only because a sign appears across 10–30 consecutive frames as you
approach it. Not survivable if anyone judges the system on one still.

These are lower than the previous run (R 0.820, mAP50 0.876) **but the two do not
share a val set** — `build` re-splits by clip every time a batch lands, so the
exam changed at the same moment the model did. Treat the drop as unmeasured, not
as a regression. Freezing a val set is the open item.

**M2** — 1151 held-out real crops. Both checkpoints scored on the *same* crops,
so this comparison is honest:

| | all 1151 crops | macro over 12 displayed | dash stays quiet | `information` (137) |
|---|---|---|---|---|
| **current (3 batches)** | **83.7%** | 86.3% | 92.8% | 85.4% |
| previous (2 batches) | 77.7% | 87.3% | 88.9% | 94.2% |

Quote **83.7%**, not a macro. Six of the displayed classes have 5–13 val crops,
so one crop moves that class 8–20 points and the macro headline is noise. (An
earlier 93.6% was exactly that and has been withdrawn — see `JOURNAL.md`,
2026-11-16.)

**The trade worth knowing:** +6.0 points overall and +3.9 on staying quiet, paid
for with −8.8 on `information`, the class the dash cares most about. b02-2's
review deleted 653 boxes as `not_a_sign` — billboards, shop fronts, bus-stop
boards, exactly what the rule in `classes.py` says to delete — and those became
training crops. M2 now rejects board-shaped things harder than it used to, and
is over-applying it to real guide signs. It fails quiet rather than wrong, which
is the safe direction, but it is still a miss.

`keep_right` has no val data at all. Anything M2 says about it is a guess with a
confident number on it.

## The AI HAT — not done yet

**`run.py` does not use the Hailo accelerator.** It runs both models on the Pi's
CPU through PyTorch. Expect single-digit fps; the numbers above are a Mac with
MPS. This is on purpose — prove the pipeline end to end first, then make it fast.

To actually use the HAT, both models have to become `.hef`:

```
m1.pt ──► ONNX ──► Hailo DFC (parse → optimize/quantize → compile) ──► m1.hef
m2.pt ──► ONNX ──► Hailo DFC                                       ──► m2.hef
```

Three things worth knowing before you start:

- **The Dataflow Compiler needs an x86_64 Linux host.** It does not run on the
  Pi, and it does not run on an Apple Silicon Mac. You need a PC, a VM, or a
  cloud box, plus a free Hailo Developer Zone account.
- **Quantization is to int8 and it is not free.** The optimize step wants
  calibration images — use real crops from `autolabel/dataset/`, not synthetic
  ones. Re-measure both models after conversion. A number from the `.pt` does
  not transfer to the `.hef`.
- **Target the right chip.** AI HAT+ 13 TOPS is `hailo8l`, 26 TOPS is `hailo8`.
  Compiling for the wrong one produces a file that will not load.

M2 is the easier half — a plain MobileNetV3-Small classifier with no NMS. M1 is
the one that will cost an afternoon, because YOLO export and NMS placement is
where this usually goes wrong.

Ultralytics documents the YOLO side:
<https://docs.ultralytics.com/integrations/hailo>

## Refreshing these files

They are copies. The originals stay with their training runs:

```bash
cd adas/experiments/central/sign_v3
cp ../../traffic-sign_recognition/thai-traffic-sign-labs/thai-traffic-sign-v3/m1/b02-2/best-m1-b02-2.pt m1.pt
cp ../../traffic-sign_recognition/thai-traffic-sign-labs/thai-traffic-sign-v3/m2_classifier.pt m2.pt
shasum -a 256 *.pt
python run.py --selfcheck
```

Update the sha column above when you do. The selfcheck catches the case that
actually bites: a new `m2.pt` trained with a different crop size or class count.

## The test clip

`../test-clip.mp4` — 2 minutes, 1920×1080 at 50 fps, 143 MB.

**It is not in git and cannot be** — past GitHub's 100 MB per-file limit. Copy it
to the Pi by hand (`scp`), or point `run.py` at any dashcam clip you already have
there.
