# Compiling sign_v3 (.pt) to the AI HAT (.hef)

How `adas/experiments/central/sign_v3/m1.pt` and `m2.pt` (b02-2, commit `b44b454`)
were compiled for the Raspberry Pi's AI HAT+ 2 (Hailo-10H) on 2026-11-16, step by
step, with the exact commands, what went wrong on the way, and what has and has
not been checked. Times are local (UTC+7).

Everything here ran on the Windows laptop, in WSL. The Pi only runs the result:
Hailo's compiler (the Dataflow Compiler, DFC) is Linux x86_64 only.

> **Not committed yet.** `tools/export_m2_hailo.py`, the `--finetune-batch`
> option in `tools/export_hailo.py` and this file are in the `feature/live-signs`
> worktree (`D:\GitHub\modular-adas-live`) as uncommitted changes.

---

## 0. What was used

| | |
|---|---|
| PC | Windows 11, i9-13980HX, RTX 4070 Laptop GPU (8 GB), NVIDIA driver 555.97 |
| WSL | Ubuntu 24.04.1 LTS, Python 3.12.3 |
| Hailo DFC | `hailo_dataflow_compiler-5.5.0-py3-none-linux_x86_64.whl` (Hailo Developer Zone, free account) |
| Python packages (venv `~/hailo`) | ultralytics 8.4.211, torch 2.9.1 (+cu128), torchvision 0.24.1, tensorflow 2.19.1, onnx 1.17.0, numpy 1.26.4, opencv-python(-headless) 4.11.0.86, nvidia-cudnn-cu12 9.10.2.21, nvidia-cuda-nvcc-cu12 12.8.93 |
| Target | `hailo10h` |
| Pi runtime | HailoRT 5.1.1 (`hailo_platform`), Raspberry Pi 5 8 GB |
| Models | `m1.pt` sha256 `69a75ce304ad…`, `m2.pt` sha256 `7efca804bb4f…` |
| Calibration clip | `C:\Users\phatt\Downloads\20260322135756_020713A.MP4` (2560×1440, 30 fps, 5400 frames) |

Check the model hashes before you start (they must match the table in
`sign_v3/README.md`):

```bash
sha256sum m1.pt m2.pt | cut -c1-12
```

---

## 1. One-time WSL setup

### 1.1 Give WSL enough memory

M1 is compiled at 1280×1280, and WSL's default (half the RAM) is not enough.
`C:\Users\phatt\.wslconfig`:

```ini
[wsl2]
memory=24GB
swap=32GB
```

Then `wsl --shutdown` from Windows and start Ubuntu again.

### 1.2 The venv, the DFC, then ultralytics pinned around it

Order matters: install the DFC first, freeze what it brought, and install
ultralytics *constrained to those versions*, so pip doesn't upgrade a package
the DFC depends on.

```bash
python3 -m venv ~/hailo && . ~/hailo/bin/activate
pip install /mnt/c/Users/phatt/Downloads/hailo_dataflow_compiler-5.5.0-py3-none-linux_x86_64.whl
pip freeze > /tmp/dfc-pins.txt
pip install -c /tmp/dfc-pins.txt ultralytics==8.4.211 opencv-python-headless
```

On first use the DFC runs a system check that reports `python3-tk`,
`graphviz`, `libgraphviz-dev` and `python3.12-dev` as missing and CUDA/cuDNN
as "X" (it looks for a system CUDA, not the pip one). It then asks
`Continue? [Y/n]` with a 60 s timeout; unanswered, it logs
`No response - exiting.`. **That exits the check only, not the compile**:
both compiles below carried on past it. To silence it, install the four apt
packages (`sudo apt install python3-tk graphviz libgraphviz-dev python3.12-dev`).
That wasn't done here.

### 1.3 Let TensorFlow (inside the DFC) use the GPU

The DFC's optimisation step is TensorFlow, and it runs on the CPU if no GPU
is usable. With the GPU visible but no CUDA compiler, an earlier attempt
failed with `JIT compilation failed. [Op:Log]` (XLA can't find `ptxas` /
`libdevice`). As a workaround, the older builds ran CPU-only with
`CUDA_VISIBLE_DEVICES=""`.

Fix: install the CUDA compiler from pip (matching the other cu12.8 packages)
and point XLA at it:

```bash
. ~/hailo/bin/activate
pip install "nvidia-cuda-nvcc-cu12==12.8.93"
```

`~/v3/gpuenv.sh`, sourced before every compile:

```bash
# source me: TF in ~/hailo on the GPU, with XLA finding pip's nvcc + libdevice
source ~/hailo/bin/activate
NV=$HOME/hailo/lib/python3.12/site-packages/nvidia
export XLA_FLAGS=--xla_gpu_cuda_data_dir=$NV/cuda_nvcc
export PATH=$NV/cuda_nvcc/bin:$PATH
export TF_CPP_MIN_LOG_LEVEL=1
unset CUDA_VISIBLE_DEVICES
```

Check: a small TF script listed `GPU:0`, ran an XLA-JIT matmul and a Keras
`fit` with `jit_compile=True` without error. TF reported 5520 MB of the 8 GB
usable. That limit matters in step 3.

---

## 2. Working folder

```bash
mkdir -p ~/v3
cp /mnt/d/GitHub/modular-adas/adas/experiments/central/sign_v3/{m1.pt,m2.pt} ~/v3/
cp /mnt/d/GitHub/modular-adas-live/adas/vision/tools/export_hailo.py ~/v3/
cp /mnt/d/GitHub/modular-adas-live/adas/vision/tools/export_m2_hailo.py ~/v3/
cd ~/v3 && source gpuenv.sh
```

(From Git Bash on Windows, `wsl -d Ubuntu -- bash -lc '…'` re-parses the
string in a second shell and expands `$VAR`s early; `wsl -d Ubuntu -e bash -lc
'…'` doesn't. Scripts written on Windows need `tr -d '\r'` before bash runs them.)

---

## 3. M1: the sign finder (YOLO26n @ 1280, one class)

M1 is an ultralytics YOLO, so ultralytics' own Hailo export does the work;
`export_hailo.py` only supplies calibration frames and one setting.

```bash
python export_hailo.py \
    --clip /mnt/c/Users/phatt/Downloads/20260322135756_020713A.MP4 \
    --weights ~/v3/m1.pt --frames 256 --work ~/hailo-calib-256 \
    --out ~/v3/m1_hailo_model --finetune-batch 2 > m1.log 2>&1
```

What happens, in order:

1. **Calibration frames.** 256 frames, every 21st of the clip's 5400, resized to
   1280×720, the dashcam's date/GPS strip (bottom right) blacked out, saved as
   JPEGs in `~/hailo-calib-256/images/train`. These were already there from an
   earlier build (log: `calibration: reusing …`); the file names
   (`f000000`, `f000021`, …) match that clip's frame count. No labels.
2. **ONNX.** ultralytics exports opset 11, simplifies it with onnxslim
   (9.9 MB).
3. **Translate.** `ClientRunner(hw_arch="hailo10h").translate_onnx_model(...)`.
4. **Model script.** ultralytics writes it (`ultralytics/engine/exporter.py`,
   ~line 1837, read from the code, not the log): normalisation `[0,0,0]` /
   `[255,255,255]` on the chip; `optimization_level=2`; quantisation-aware
   fine-tuning (QFT) on all 256 images; and, because YOLO26 is DFL-free
   (`reg_max == 1`), its raw box/score outputs kept at 16 bit (`a16_w16`) and
   **no NMS on the chip** (`metadata.yaml`: `nms: false`, `end2end: false`).
   NMS runs on the Pi in `signs/hailo10.py`. `--finetune-batch 2` adds
   `batch_size=2` to the fine-tune line by patching
   `ClientRunner.load_model_script` (see step 3.1).
5. **Optimise (INT8).** Statistics on 64 images, then QFT on 256 for
   4 epochs: **9 min 02 s** on the GPU (81% busy, 5.7 GB).
6. **Layer noise analysis**, 4 min 18 s, **produced no numbers**: it ran out of
   GPU memory itself (`Layer Noise Analysis will not generate statistics`).
   So there is **no SNR figure for M1**.
7. **Compile.** CPU only, single-threaded: partition search, 5 contexts,
   **8 min 16 s**.
8. Output: `~/v3/m1_hailo_model/m1.hef` (4,521,984 bytes, 23:51:55) and
   `metadata.yaml`.

Start to finish about 25 minutes (≈23:27 → 23:52).

### 3.1 What went wrong first

* **QFT out of GPU memory.** The first GPU attempt died in QFT with
  `AccelerasResourceError: GPU memory has been exhausted. Please try to use
  Quantization-Aware Fine-Tuning with lower batch size or run on CPU.` The
  DFC's QFT batch defaults to the calibration batch size, 8
  (`hailo_model_optimization/acceleras/utils/acceleras_definitions.py`:
  `DEFAULT_BATCH_SIZE = 8`). Batch 2 fits. The DFC scales the learning rate
  with the batch (`qft.py`, `fill_finetune_defaults`), so batch 2 trains at a
  quarter of the default rate. Whether that makes M1 better or worse than
  batch 8 would has **not been measured**.
* **Correction to what I said during the session:** I said QFT only runs
  with a GPU and that the earlier CPU build skipped it. **That was wrong.**
  The earlier build (19:17, CPU-only, the previous `m1.pt`) ran QFT too:
  10 min 45 s on 64 images. The real difference is 256 images instead of 64,
  on the GPU instead of the CPU.

---

## 4. M2: the classifier (MobileNetV3-Small @ 128, 29 classes)

M2 is a plain torchvision model, so ultralytics doesn't apply.
`export_m2_hailo.py` drives the DFC directly.

```bash
python export_m2_hailo.py \
    --clip /mnt/c/Users/phatt/Downloads/20260322135756_020713A.MP4 \
    --m1 ~/v3/m1.pt --m2 ~/v3/m2.pt \
    --out ~/v3/m2_hailo_model --work ~/hailo-calib-m2 > m2.log 2>&1
```

1. **ONNX.** `torch.onnx.export`, opset 13, input `crop` `[1,3,128,128]`,
   output `logits` (29). The class list, the 13 displayed classes and the crop
   size go to `m2.json` beside the .hef.
2. **Calibration crops.** M1 (the `.pt`, via ultralytics, conf 0.25, 1280)
   runs over ~600 frames spread across the clip, with the OSD strip blacked
   out. Every box ≥ 24 px on its short side becomes a 128 px crop, cut exactly
   as `sign_v3/run.py`'s `square()` cuts it (squared on the box centre,
   clamped to the frame, Lanczos), plus random patches of road for the
   `not_a_sign` end. 1024 crops in total, cached as
   `~/hailo-calib-m2/m2_calib_128.npy`. The split between sign crops and road
   patches was printed by the first run, but that log was overwritten and I
   don't have the numbers.
3. **Model script:**
   ```
   normalization1 = normalization([123.675, 116.28, 103.53], [58.395, 57.12, 57.375])
   quantization_param([m2/dw1], precision_mode=a16_w16)
   ```
   The first line is M2's ImageNet normalisation, done on the chip, so the Pi
   sends plain RGB bytes. The second line keeps the first depthwise conv at
   16 bit (see 4.1); it's the default of the new `--a16` option.
4. **Optimise.** Default optimisation level (none set in the script). QFT on
   1024 crops, 2 min 11 s on the GPU.
5. **Compile.** 3 contexts, 2 min 1 s (the all-INT8 build took 1 min 0 s).
6. Output: `~/v3/m2_hailo_model/m2.hef` (2,150,400 bytes, 23:59:20) + `m2.json`.
   Output-layer SNR **13.28 dB**.

### 4.1 Why `dw1` is 16-bit

The first M2 build (23:25, all INT8) reported output SNR 12.05 dB and flagged
`m2/dw1` at 3.15 dB partial SNR, suggesting
`quantization_param([m2/dw1], precision_mode=a16_w16)`. On the Pi (step 6) that
build disagreed with PyTorch on 13% of crops, including 4 `speed_limit` crops
it called `not_a_sign`. The rebuild with `dw1` at 16 bit fixed most of that.
The rebuild now flags `m2/normalization1` at 9.72 dB; that suggestion has
**not** been tried. The INT8 build is kept on the Pi as
`sign_v3/m2_int8_old/` and in WSL as `~/v3/m2_hailo_model.int8/`.

---

## 5. To the Pi

```bash
# from Git Bash on the PC
wsl -d Ubuntu -e bash -c 'tar -C ~/v3 -cf - m1_hailo_model m2_hailo_model' \
  | ssh w124 'tar -C ~/modular-adas/adas/experiments/central/sign_v3 -xf -'
```

`config.py` uses a `*_hailo_model` folder whenever it exists (and HailoRT is
installed), and the `.pt` otherwise. The service says which it picked:

```
signs: sign_v3, M1 m1_hailo_model on the AI HAT, M2 m2_hailo_model on the AI HAT
```

On the Pi, M1 runs pipelined (3 frames in flight) and M2 runs one crop at a
time on the same VDevice, in `signs/hailo10.py`.

---

## 6. What has been checked, and how

| Check | Result | Caveat |
|---|---|---|
| Both .hef files load on the Pi (HailoRT 5.1.1) and run | yes | — |
| **M2 on the HAT vs `m2.pt` in PyTorch**, same 1024 crops, top-1 agreement | INT8: 86.9%. **dw1 16-bit: 98.6%**. Mean confidence gap where they agree: 0.179 → 0.027. Displayed-or-not agreement: 97.9% → 99.3%. 2.2 ms/crop on the HAT | **Not held out.** These are the calibration crops. It measures how well the HAT copies PyTorch, not how often M2 is right. |
| M1 on the HAT vs `m1.pt` in PyTorch | **not done** | Layer noise analysis gave no numbers either (step 3, item 6). |
| End to end, `~/clips/front.mp4` (1440p dashcam) | announced 30 at 31.5 s, 50 at 52.5 s and 73.8 s | Matches what b01 found on that clip. Not checked frame by frame. |
| End to end, `central/test-clip.mp4` (1080p50, 2 min) | 2 announcements, **both wrong**: a no-parking sign → `speed_limit` (no number); an overhead lane-arrow board → `keep_left_or_right` | Not known whether that's M2 itself or the HAT copy of it. |
| End to end, `central/2026_0912_012925.MP4` (2304×1296, 3 min) | 30 at 46.2 s (school-zone board) and 45 at 87.7 s (yellow speed-camera board), **both right**, checked against the frames | Misses aren't counted: only the 13 displayed classes are reported. |
| Speed on the HAT | 26.6 fps average on the last two clips; HAT about 50% busy, 49–50 ms latency | Limited by the Pi's CPU (decoding, crops), not the HAT. |

## 7. Open items

* M1: compare the .hef against `m1.pt` on a set of frames (box recall and IoU),
  since the DFC's own analysis didn't run.
* M1: try QFT batch 4, or more calibration frames (ultralytics and Hailo
  suggest ≥ 1024). Each needs a memory check on the 8 GB GPU.
* M2: score both the .hef and `m2.pt` on held-out labelled crops (the 1151 val
  crops in the b02-2 commit), not the calibration crops.
* M2: try `normalization1` at 16 bit, as the DFC suggests.
* Install the four apt packages so the DFC's system check passes.
