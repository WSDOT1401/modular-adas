#!/usr/bin/env python3
"""Score M2 in the DFC's emulator before compiling, which is what we should
have done the first time.

    python check_m2_quant.py --m2 ~/v3/m2.pt            # step 2: measure only
    python check_m2_quant.py --m2 ~/v3/m2.pt --compile  # step 3: also write m2.hef

The .hef built on 2026-11-16 scored 61.9% against m2.pt's 83.7% on 1151
held-out crops, and only ever emitted 8 of 29 classes. We measured the end of
the chain and so could not say which link broke. This runs the same crops
through three stages and prints all three:

  torch           m2.pt itself. The number to match. Expect ~83.7%.
  FP_OPTIMIZED    float, after the model script (normalization, a16 layers).
                  If this is already broken, quantization was never the
                  problem -- suspect the ONNX parse or the normalization, and
                  recompiling with better calibration data will not help.
  QUANTIZED       emulated INT8, using --calib. This is what the .hef will do.

Needs the DFC (Linux x86_64 / WSL). --calib and --val come off the Mac:
build_m2_calib.py and pack_m2_val.py write them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

READABLE = 24
MIN_N = 5          # same as train_m2.py: below this a per-class % is noise


def load_torch(m2: str):
    import torch
    import torch.nn as nn
    from torchvision.models import mobilenet_v3_small

    ck = torch.load(m2, weights_only=False, map_location="cpu")
    net = mobilenet_v3_small()
    net.classifier[3] = nn.Linear(1024, len(ck["classes"]))
    net.load_state_dict(ck["state_dict"])
    net.eval()
    return net, ck


def torch_predict(net, crops: np.ndarray, batch: int) -> np.ndarray:
    import torch

    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    out = []
    with torch.no_grad():
        for i in range(0, len(crops), batch):
            x = torch.from_numpy(crops[i:i + batch]).permute(0, 3, 1, 2).float() / 255.0
            out.append(net((x - mean) / std).argmax(1).numpy())
    return np.concatenate(out)


def hailo_predict(runner, context, crops: np.ndarray, batch: int) -> np.ndarray:
    """crops are raw RGB 0-255: the normalization lives in the model script."""
    out = []
    with runner.infer_context(context) as ctx:
        for i in range(0, len(crops), batch):
            r = runner.infer(ctx, crops[i:i + batch].astype(np.float32))
            out.append(np.asarray(r).reshape(len(r), -1).argmax(1))
    return np.concatenate(out)


def report(title: str, pred: np.ndarray, labels: np.ndarray, names, baseline=None):
    acc = (pred == labels).mean()
    line = f"\n{title}: {acc:.1%}  ({int((pred == labels).sum())}/{len(labels)})"
    if baseline is not None:
        line += f"   [{acc - baseline:+.1%} vs torch]"
    print(line)
    emitted = sorted({names[p] for p in pred})
    print(f"  emits {len(emitted)} of {len(names)} classes")
    if len(emitted) < len(names) // 2:
        print(f"  ONLY: {', '.join(emitted)}")
    dead = []
    for i, name in enumerate(names):
        n = int((labels == i).sum())
        if n >= MIN_N:
            hit = int(((labels == i) & (pred == i)).sum())
            if hit == 0:
                dead.append(f"{name} (0/{n})")
    if dead:
        print(f"  ZERO on: {', '.join(dead)}")
    return acc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--m2", required=True)
    ap.add_argument("--calib", default=str(Path.home() / "hailo-calib-m2" / "m2_calib_128.npy"))
    ap.add_argument("--val", default=str(Path.home() / "hailo-calib-m2" / "m2_val_128.npz"))
    ap.add_argument("--target", default="hailo10h", choices=("hailo10h", "hailo8", "hailo8l"))
    ap.add_argument("--a16", nargs="*", default=["dw1"], metavar="LAYER")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--opt-level", type=int, help="DFC optimization level (default 2). 3-4 enable "
                                                  "Bias Correction and AdaRound, which log as 'skipped' at 2")
    ap.add_argument("--calibset", type=int, help="crops the Statistics Collector uses to set activation "
                                                 "ranges (DFC default 64, even when you hand it 1024)")
    ap.add_argument("--script-extra", default="", help="extra model-script lines, ';' separated")
    ap.add_argument("--compile", action="store_true", help="write the .hef if the emulator looks right")
    ap.add_argument("--out", default=str(Path.home() / "v3" / "m2_hailo_model"))
    ap.add_argument("--work", default=str(Path.home() / "hailo-calib-m2"))
    args = ap.parse_args()

    import torch
    from hailo_sdk_client import ClientRunner
    try:
        from hailo_sdk_client import InferenceContext
    except ImportError:
        from hailo_sdk_common.targets.inference_targets import InferenceContext

    val = np.load(args.val, allow_pickle=False)
    crops, labels = val["crops"], val["labels"].astype(np.int64)
    calib = np.load(args.calib)
    print(f"val   {crops.shape}  {len(set(labels.tolist()))} classes present")
    print(f"calib {calib.shape}  from {args.calib}")

    net, ck = load_torch(args.m2)
    names, displayed, size = list(ck["classes"]), list(ck["displayed"]), int(ck["size"])
    assert crops.shape[1:] == (size, size, 3), f"val crops are not {size}px"
    assert calib.shape[1:] == (size, size, 3), f"calib crops are not {size}px"
    print(f"model {len(names)} classes, {len(displayed)} displayed, {size}px")

    base = report("torch   (m2.pt)", torch_predict(net, crops, args.batch), labels, names)

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    onnx = work / "m2.onnx"
    torch.onnx.export(net, torch.zeros(1, 3, size, size), str(onnx), opset_version=13,
                      input_names=["crop"], output_names=["logits"], dynamo=False)

    runner = ClientRunner(hw_arch=args.target)
    runner.translate_onnx_model(str(onnx), "m2", start_node_names=["crop"], end_node_names=["logits"],
                                net_input_shapes={"crop": [1, 3, size, size]})
    script = ("normalization1 = normalization([123.675, 116.28, 103.53], "
              "[58.395, 57.12, 57.375])\n")
    if args.a16:
        script += f"quantization_param([{', '.join('m2/' + l for l in args.a16)}], precision_mode=a16_w16)\n"
    if args.opt_level is not None:
        script += f"model_optimization_flavor(optimization_level={args.opt_level}, compression_level=0)\n"
    if args.calibset is not None:
        script += f"model_optimization_config(calibration, calibset_size={args.calibset})\n"
    for line in filter(None, args.script_extra.split(";")):
        script += line.strip() + "\n"
    print("\nmodel script:\n" + "".join("  " + l + "\n" for l in script.strip().split("\n")))
    runner.load_model_script(script)

    print("optimizing (this is the slow part) ...")
    runner.optimize(calib)

    fp = report("FP_OPTIMIZED", hailo_predict(runner, InferenceContext.SDK_FP_OPTIMIZED, crops, args.batch),
                labels, names, base)
    q = report("QUANTIZED (= the .hef)",
               hailo_predict(runner, InferenceContext.SDK_QUANTIZED, crops, args.batch),
               labels, names, base)

    print("\n" + "-" * 60)
    if fp < base - 0.05:
        print("FP_OPTIMIZED is already broken: this is NOT a calibration problem.")
        print("Suspect the ONNX parse or the normalization in the model script.")
    elif q < base - 0.05:
        print(f"Quantization is the culprit, confirmed. {q:.1%} vs {base:.1%} float.")
        print("Scroll up to 'Output layers signal-to-noise ratio'. If that SNR is low,")
        print("the DFC names the layers to promote -- re-run with --a16 dw1 <those>.")
    else:
        print(f"Quantization holds: {q:.1%} vs {base:.1%} float. Compile it.")
    print(f"previous .hef on these same crops: 61.9%")

    if args.compile:
        hef = runner.compile()
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "m2.hef").write_bytes(hef)
        (dest / "m2.json").write_text(json.dumps(
            {"classes": names, "displayed": displayed, "size": size, "readable": READABLE},
            indent=1) + "\n")
        print(f"\ncompiled -> {dest}  (emulator said {q:.1%})")
        print("copy that folder to the same place on the Pi")
    else:
        print("\nno --compile, nothing written. Re-run with --compile to build the .hef.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
