#!/usr/bin/env python3
"""Compile sign_v3's M2 (the 29-class crop classifier) for the Pi's AI HAT.

M2 is a torchvision MobileNetV3-Small on 128 px square crops, not a YOLO, so
ultralytics' Hailo export doesn't apply: this exports it to ONNX and runs
Hailo's Dataflow Compiler on it directly (parse -> INT8 optimise -> compile).
Like tools/export_hailo.py, it needs Linux x86_64 (on Windows: WSL) with the
DFC installed, never the Pi.

Calibration: INT8 needs crops that look like what M2 will see, so they are
real ones. M1 runs over a dashcam clip and every box it finds becomes a crop
cut exactly as on the Pi (signs/v3.py: squared around the box, nothing under
24 px, resized with Lanczos), plus a few random patches of road for the
not_a_sign end. Prefer the balanced set from the labelled crops instead:
run thai-traffic-sign-v3/build_m2_calib.py and drop its .npy in --work.

The defaults here are the config that works. Optimization level 4 (AdaRound)
is the one that matters: at the DFC default of 2 this builds a model that only
ever predicts 10 of 29 classes -- 12.8% macro recall on held-out crops, zero on
stop signs. See JOURNAL.md 2026-11-18. Score any build with check_m2_quant.py
before compiling, and score_m2_hef.py on the Pi after.

The ImageNet normalisation M2 was trained with is compiled into the .hef, so
the Pi feeds it plain RGB bytes. Out come 29 logits; softmax is on the Pi.

    python tools/export_m2_hailo.py --clip /mnt/c/Users/me/Downloads/drive.mp4
    # -> adas/experiments/central/sign_v3/m2_hailo_model/ (m2.hef + m2.json)

m2.json carries what m2.pt carried besides the weights: the class list, the
13 the dash shows, the crop size.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

VISION = Path(__file__).resolve().parents[1]
V3 = VISION.parent / "experiments" / "central" / "sign_v3"
READABLE = 24       # same as sign_v3/run.py and signs/v3.py
OSD = (slice(1300, None), slice(1280, None))     # dashcam date/GPS strip at 2560x1440


def square(im, x1, y1, x2, y2, size):
    """sign_v3/run.py's square(), unchanged: M2 was trained on exactly this."""
    from PIL import Image  # type: ignore

    half = min(max(x2 - x1, y2 - y1) / 2, im.width / 2, im.height / 2)
    cx = min(max((x1 + x2) / 2, half), im.width - half)
    cy = min(max((y1 + y2) / 2, half), im.height - half)
    return im.crop((round(cx - half), round(cy - half),
                    round(cx + half), round(cy + half))).resize((size, size), Image.LANCZOS)


def calibration(clip: str, m1: str, size: int, count: int, out: Path):
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    from PIL import Image  # type: ignore
    from ultralytics import YOLO  # type: ignore

    cache = out / f"m2_calib_{size}.npy"
    if cache.is_file():
        data = np.load(cache)
        if len(data) >= count:
            print(f"calibration: reusing {cache}")
            return data[:count]
    if not clip:
        sys.exit(f"no --clip and no {cache}: run build_m2_calib.py and copy its .npy there")
    det = YOLO(m1)
    cap = cv2.VideoCapture(clip)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        sys.exit(f"can't read {clip}")
    rng = random.Random(0)
    signs, road = [], []
    for i in range(0, total, max(1, total // 600)):        # ~600 frames across the clip
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            continue
        if frame.shape[0] == 1440:
            frame[OSD] = 0
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        for b in det.predict(frame, imgsz=1280, conf=0.25, verbose=False)[0].boxes.xyxy.tolist():
            if min(b[2] - b[0], b[3] - b[1]) >= READABLE:
                signs.append(np.asarray(square(pil, *b, size)))
        s = rng.randint(32, 160)                               # a patch of anything
        x, y = rng.randint(0, pil.width - s), rng.randint(0, pil.height // 2)
        road.append(np.asarray(square(pil, x, y, x + s, y + s, size)))
    cap.release()
    rng.shuffle(road)
    crops = signs + road[: max(count // 4, count - len(signs))]
    rng.shuffle(crops)
    print(f"calibration: {len(signs)} sign crops + {len(crops) - len(signs)} road patches")
    if len(crops) < 64:
        sys.exit("too few crops for calibration: is that the right clip?")
    data = np.stack(crops[:count]).astype(np.float32)          # NHWC RGB 0-255
    out.mkdir(parents=True, exist_ok=True)
    np.save(cache, data)
    return data


def export_onnx(m2: str, path: Path) -> dict:
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
    from torchvision.models import mobilenet_v3_small  # type: ignore

    ck = torch.load(m2, weights_only=False, map_location="cpu")
    net = mobilenet_v3_small()
    net.classifier[3] = nn.Linear(1024, len(ck["classes"]))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    size = int(ck["size"])
    torch.onnx.export(net, torch.zeros(1, 3, size, size), str(path), opset_version=13,
                      input_names=["crop"], output_names=["logits"], dynamo=False)
    return {"classes": list(ck["classes"]), "displayed": list(ck["displayed"]),
            "size": size, "readable": READABLE}


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile sign_v3 m2.pt to a Hailo .hef")
    ap.add_argument("--clip", help="dashcam clip: M1 cuts the calibration crops from it. Omit when\n                         --work already holds an m2_calib_<size>.npy -- build_m2_calib.py\n                         writes a balanced one and a one-clip set is what broke the last .hef")
    ap.add_argument("--m1", default=str(V3 / "m1.pt"))
    ap.add_argument("--m2", default=str(V3 / "m2.pt"))
    ap.add_argument("--target", default="hailo10h", choices=("hailo10h", "hailo8", "hailo8l"))
    ap.add_argument("--crops", type=int, default=1024, help="calibration crops")
    ap.add_argument("--out", default=str(V3 / "m2_hailo_model"))
    ap.add_argument("--work", default=str(Path.home() / "hailo-calib-m2"))
    ap.add_argument("--a16", nargs="*", metavar="LAYER",
                    default=["dw1", "dw7", "normalization1", "dw4", "dw9", "dw5", "conv41"],
                    help="layers kept at 16 bits. Worth little on its own (+3 points, then -1 "
                         "for the next three) -- the DFC names a different triple every round, "
                         "which is error spread over the whole net, not one culprit")
    ap.add_argument("--opt-level", type=int, default=4,
                    help="DFC optimization level. 4 runs AdaRound (~23 min); the default 2 logs "
                         "'Quantization-Aware Fine-Tuning skipped' and runs plain QFT. This is "
                         "the setting that fixed M2: output SNR 0.73 -> 4.63 dB, 47.7% -> 75.3%")
    ap.add_argument("--calibset", type=int, default=1024,
                    help="crops the Statistics Collector uses for activation ranges. It defaults "
                         "to 64 even when handed 1024, and sets every range off those 64")
    args = ap.parse_args()

    from hailo_sdk_client import ClientRunner  # type: ignore

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    onnx = work / "m2.onnx"
    meta = export_onnx(args.m2, onnx)
    calib = calibration(args.clip, args.m1, meta["size"], args.crops, work)

    runner = ClientRunner(hw_arch=args.target)
    runner.translate_onnx_model(str(onnx), "m2", start_node_names=["crop"], end_node_names=["logits"],
                                net_input_shapes={"crop": [1, 3, meta["size"], meta["size"]]})
    # M2's ImageNet normalisation, on the chip: the Pi sends RGB bytes.
    script = ("normalization1 = normalization([123.675, 116.28, 103.53], "
              "[58.395, 57.12, 57.375])\n")
    if args.a16:
        script += f"quantization_param([{', '.join('m2/' + l for l in args.a16)}], precision_mode=a16_w16)\n"
    script += f"model_optimization_flavor(optimization_level={args.opt_level}, compression_level=0)\n"
    script += f"model_optimization_config(calibration, calibset_size={args.calibset})\n"
    print("\nmodel script:\n" + "".join("  " + l + "\n" for l in script.strip().split("\n")))
    runner.load_model_script(script)
    runner.optimize(calib)
    hef = runner.compile()

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "m2.hef").write_bytes(hef)
    (dest / "m2.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"\ncompiled for {args.target}: {dest}\ncopy that folder to the same place on the Pi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
