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
| `m1.pt` | class-agnostic sign detector, yolo26n @1280 | 5.3 MB | `cbbd77fe1c99` |
| `m2.pt` | 29-class crop classifier, MobileNetV3-Small @128 | 6.0 MB | `18c347e2ccba` |
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

**M1** — `m1-floor16-b01b02`, yolo26n, 50 epochs, imgsz 1280, `fliplr=0`:

| P | R | mAP50 | mAP50-95 |
|---|---|---|---|
| 0.852 | **0.820** | 0.876 | 0.741 |

Read the recall honestly: **it misses about 1 sign in 5.6 on a single frame.**
Survivable only because a sign appears across 10–30 consecutive frames as you
approach it. Not survivable if anyone judges the system on one still.

**M2** — 996 held-out real crops, after a full human review pass:

| all 996 crops | macro over the 11 scored displayed classes | dash stays quiet | `information` (154 crops) |
|---|---|---|---|
| **90.3%** | 87.7% | 94.3% | **100%** |

Quote **90.3%**, not a macro. Six of the displayed classes have 5–13 val crops,
so one crop moves that class 8–20 points and the macro headline is noise. (An
earlier 93.6% was exactly that and has been withdrawn — see `JOURNAL.md`,
2026-11-16.)

`keep_right` and `right_curve` have almost no val data. Anything M2 says about
them is a guess with a confident number on it.

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
cp ../../traffic-sign_recognition/thai-traffic-sign-labs/thai-traffic-sign-v3/m1/b02-1/best-m1-b02-1.pt m1.pt
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
