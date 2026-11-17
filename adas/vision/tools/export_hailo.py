#!/usr/bin/env python3
"""Compile the b01 sign detector for the Hailo chip on the Pi's AI HAT.

The Hailo can't run a .pt: the model has to be quantised to INT8 and compiled
into a .hef. That needs Hailo's Dataflow Compiler, which only runs on Linux
x86_64 (on Windows: WSL), never on the Pi. Ultralytics drives the whole
thing; this script only supplies the calibration images and the settings
that matter for b01.

Calibration: INT8 needs ~1000 frames that look like what the camera will
see, to pick the number ranges. They come from a dashcam clip, evenly spaced,
at 1280 wide, with the dashcam's burned-in date/GPS strip blacked out (the Pi
camera won't have it). Labels aren't needed.

Setup, once, in WSL (Ubuntu):
    python3 -m venv ~/hailo && . ~/hailo/bin/activate
    pip install ultralytics opencv-python-headless
    pip install hailo_dataflow_compiler-5.*-linux_x86_64.whl   # Hailo Developer Zone, free account

Then:
    python tools/export_hailo.py --clip /mnt/c/Users/me/Downloads/drive.mp4
    # -> adas/experiments/central/b01_hailo_model/  (b01.hef + metadata.yaml)

Copy that folder to the same place on the Pi; the vision service uses it
instead of b01.pt whenever it is there (config.SIGN_WEIGHTS).

Targets: hailo10h = AI HAT+ 2 (the default), hailo8 = AI HAT+ 26 TOPS,
hailo8l = AI HAT+ 13 TOPS / AI Kit.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

VISION = Path(__file__).resolve().parents[1]
CENTRAL = VISION.parent / "experiments" / "central"
# The dashcam's date/GPS text (bottom right of a 1280x720 frame).
OSD = (slice(650, None), slice(640, None))


def build_calibration(clip: str, out: Path, count: int, names: dict) -> Path:
    import cv2  # type: ignore

    images = out / "images" / "train"
    if images.is_dir() and len(list(images.glob("*.jpg"))) >= count:
        print(f"calibration: reusing {images}")
    else:
        images.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(clip)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            sys.exit(f"can't read {clip}")
        step = max(1, total // count)
        i = saved = 0
        while saved < count and cap.grab():
            if i % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
                    frame[OSD] = 0
                    cv2.imwrite(str(images / f"f{i:06d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    saved += 1
            i += 1
        print(f"calibration: {saved} frames from {clip}")

    yaml = out / "calib.yaml"
    lines = [f"path: {out}", "train: images/train", "val: images/train", "names:"]
    lines += [f"  {k}: {v}" for k, v in names.items()]
    yaml.write_text("\n".join(lines) + "\n")
    return yaml


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile b01.pt to a Hailo .hef")
    ap.add_argument("--clip", required=True, help="dashcam clip for the calibration frames")
    ap.add_argument("--weights", default=str(CENTRAL / "b01.pt"))
    ap.add_argument("--target", default="hailo10h", choices=("hailo10h", "hailo8", "hailo8l"))
    ap.add_argument("--imgsz", type=int, default=1280, help="b01 was trained at 1280")
    ap.add_argument("--frames", type=int, default=1024, help="calibration frames")
    ap.add_argument("--out", default=str(CENTRAL / "b01_hailo_model"),
                    help="where the compiled model folder goes")
    ap.add_argument("--work", default=str(Path.home() / "hailo-calib"),
                    help="where the calibration frames go (reused on a rerun)")
    ap.add_argument("--finetune-batch", type=int, default=2,
                    help="quantisation-aware fine-tuning batch. The DFC's default (8) runs out "
                         "of memory on an 8 GB laptop GPU at 1280 px; it scales the learning "
                         "rate to the batch itself")
    args = ap.parse_args()

    from hailo_sdk_client import ClientRunner  # type: ignore
    from ultralytics import YOLO  # type: ignore

    # Ultralytics writes the model script itself; slip the batch size into its
    # fine-tune line (it runs on the CPU too, just much slower).
    load = ClientRunner.load_model_script

    def load_model_script(self, script, *a, **k):
        script = script.replace("post_quantization_optimization(finetune, policy=enabled,",
                                "post_quantization_optimization(finetune, policy=enabled, "
                                f"batch_size={args.finetune_batch},")
        return load(self, script, *a, **k)
    ClientRunner.load_model_script = load_model_script

    model = YOLO(args.weights)
    yaml = build_calibration(args.clip, Path(args.work), args.frames, model.names)
    out = model.export(format="hailo", name=args.target, imgsz=args.imgsz, data=str(yaml))

    # Ultralytics writes <weights>_hailo_model/ next to the weights; say where.
    # A failed compile can still leave the folder behind, and the vision
    # service would then pick it up instead of b01.pt: insist on the .hef.
    out = Path(out) if out else None
    if out is None or not any(out.glob("*.hef")):
        if out is not None:
            shutil.rmtree(out, ignore_errors=True)
        sys.exit("export failed: no .hef produced (see the log above)")
    dest = Path(args.out)
    if out.resolve() != dest.resolve():
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(out), dest)
    print(f"\ncompiled for {args.target}: {dest}\ncopy that folder to the same place on the Pi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
