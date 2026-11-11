"""Benchmark the trained GTSDB detectors on a Raspberry Pi 5.

Answers the deployment question the training grid raises: 1024 is clearly more
accurate than 640, but can the Pi actually run it? For every run under
``results/`` this times the PyTorch checkpoint and both NCNN exports at the
resolution that run was trained for, and reports FPS against the cluster's
18–25 FPS budget.

Only NCNN artifacts already exported by ``train.py`` are used — nothing is
re-exported here, so what you measure is exactly what would ship.

Usage on the Pi::

    python3 benchmark_pi.py                          # everything in results/
    python3 benchmark_pi.py --runs 4class-640        # just one
    python3 benchmark_pi.py --source clip.mp4        # time against real frames

Thermal note: the Pi throttles under sustained inference, which shows up as a
slow drift in FPS rather than an error. SoC temperature is sampled before and
after each config, and ``vcgencmd get_throttled`` is reported when available.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import shutil
import subprocess
import time

HERE = pathlib.Path(__file__).resolve().parent

WARMUP, RUNS = 5, 30
TARGET_FPS = 18                 # lower bound of the cluster's 18-25 FPS goal

# label -> (subdirectory under weights/, or None for the .pt itself). The
# `_ncnn_model` suffix is what ultralytics matches on to pick the NCNN backend.
VARIANTS = {
    "PyTorch": None,
    "NCNN": "best_fp32_ncnn_model",
    "NCNN-FP16": "best_fp16_ncnn_model",
}
# Names written before the suffix bug was fixed. Unloadable as-is, so point them
# out rather than silently reporting "missing".
LEGACY_VARIANTS = {"NCNN": "best_ncnn_fp32", "NCNN-FP16": "best_ncnn_fp16"}


def soc_temp_c() -> float | None:
    """SoC temperature in °C, or None off-Pi."""
    for path in ("/sys/class/thermal/thermal_zone0/temp",):
        try:
            return int(pathlib.Path(path).read_text().strip()) / 1000.0
        except (OSError, ValueError):
            continue
    return None


def throttled_flags() -> str:
    """``vcgencmd get_throttled`` output — 0x0 means no throttling has occurred."""
    if not shutil.which("vcgencmd"):
        return "-"
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return out.split("=")[-1] or "-"
    except (OSError, subprocess.SubprocessError):
        return "-"


def load_frame(source: str | None, imgsz: int):
    """One BGR frame to time against.

    Inference cost is fixed for a given input size, but post-processing scales
    with the number of detections — so a blank synthetic frame under-reports
    NMS. A real road frame is preferred; ``--source`` accepts an image or video.
    """
    import cv2
    import numpy as np

    if source:
        path = pathlib.Path(source)
        if not path.exists():
            raise FileNotFoundError(f"--source {path} does not exist")
        if path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}:
            capture = cv2.VideoCapture(str(path))
            ok, frame = capture.read()
            capture.release()
            if not ok:
                raise RuntimeError(f"could not read a frame from {path}")
            return frame, str(path)
        frame = cv2.imread(str(path))
        if frame is None:
            raise RuntimeError(f"could not decode {path}")
        return frame, str(path)

    # Fall back to a converted GTSDB frame if the dataset happens to be here.
    for candidate in sorted((HERE / "datasets" / "_images").rglob("*.png"))[:1]:
        import cv2 as _cv2
        return _cv2.imread(str(candidate)), str(candidate)

    print("  WARNING: no --source given and no local dataset frame found; using "
          "a synthetic frame. Inference timings are valid, but post-processing "
          "will be optimistic because a blank frame yields no detections.")
    return np.zeros((imgsz, imgsz, 3), dtype=np.uint8), "synthetic"


def discover(results_dir: pathlib.Path, wanted: list[str] | None) -> list[dict]:
    """Find (run, imgsz, variant, weights path) for everything benchmarkable."""
    import json

    found: list[dict] = []
    legacy: list[pathlib.Path] = []
    for run_dir in sorted(p for p in results_dir.iterdir() if p.is_dir()):
        if wanted and run_dir.name not in wanted:
            continue
        meta_path = run_dir / "run_meta.json"
        imgsz = json.loads(meta_path.read_text())["imgsz"] if meta_path.exists() else 640
        weights = run_dir / "weights"
        for label, subdir in VARIANTS.items():
            path = weights / "best.pt" if subdir is None else weights / subdir
            if path.exists():
                found.append({"run": run_dir.name, "imgsz": imgsz,
                              "variant": label, "weights": path})
            elif subdir and (weights / LEGACY_VARIANTS.get(label, "")).exists():
                legacy.append(weights / LEGACY_VARIANTS[label])
            else:
                print(f"  missing: {run_dir.name} / {label}  ({path.name})")
    if legacy:
        print(f"\n  {len(legacy)} NCNN export(s) use the old directory name, which "
              "ultralytics cannot load\n  (it matches on the '_ncnn_model' suffix). "
              "Rename them:\n")
        for path in legacy:
            tag = "fp32" if path.name.endswith("fp32") else "fp16"
            print(f"    mv {path} {path.parent / f'best_{tag}_ncnn_model'}")
        print()
    return found


def measure(weights: pathlib.Path, frame, imgsz: int) -> dict:
    """Mean per-frame latency for one model, split into ultralytics' stages."""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    for _ in range(WARMUP):
        model.predict(frame, imgsz=imgsz, verbose=False)

    stages = {"preprocess": [], "inference": [], "postprocess": []}
    totals = []
    for _ in range(RUNS):
        started = time.perf_counter()
        result = model.predict(frame, imgsz=imgsz, verbose=False)[0]
        totals.append((time.perf_counter() - started) * 1000)
        for stage in stages:
            stages[stage].append(result.speed[stage])

    mean = lambda xs: sum(xs) / len(xs)
    total_ms = mean(totals)
    return {
        "preprocess_ms": round(mean(stages["preprocess"]), 2),
        "inference_ms": round(mean(stages["inference"]), 2),
        "postprocess_ms": round(mean(stages["postprocess"]), 2),
        "total_ms": round(total_ms, 2),
        "fps": round(1000 / total_ms, 1),
        "detections": len(result.boxes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=pathlib.Path, default=HERE / "results")
    parser.add_argument("--runs", nargs="*", default=None,
                        help="run names to benchmark (default: all found)")
    parser.add_argument("--source", default=None,
                        help="image or video to time against (strongly preferred "
                             "over the synthetic fallback)")
    parser.add_argument("--out", type=pathlib.Path, default=HERE / "results" / "pi_benchmark.csv")
    args = parser.parse_args(argv)

    if not args.results.exists():
        print(f"no results directory at {args.results} — did you `git lfs pull`?")
        return 1

    configs = discover(args.results, args.runs)
    if not configs:
        print(f"nothing benchmarkable under {args.results}.\n"
              "If weights/ holds small text files instead of real models, the LFS "
              "objects were not fetched: run `git lfs install && git lfs pull`.")
        return 1

    print(f"\nRaspberry Pi benchmark — {len(configs)} configs, "
          f"{WARMUP} warmup + {RUNS} timed runs each")
    start_temp = soc_temp_c()
    if start_temp is not None:
        print(f"SoC temp at start: {start_temp:.1f} C   throttled: {throttled_flags()}")

    rows = []
    for config in configs:
        frame, frame_label = load_frame(args.source, config["imgsz"])
        before = soc_temp_c()
        label = f"{config['run']} / {config['variant']}"
        print(f"\n  {label} @ {config['imgsz']}")
        try:
            stats = measure(config["weights"], frame, config["imgsz"])
        except Exception as exc:
            print(f"    FAILED: {type(exc).__name__}: {exc}")
            rows.append({"run": config["run"], "variant": config["variant"],
                         "imgsz": config["imgsz"], "status": f"fail: {exc}"[:80]})
            continue
        after = soc_temp_c()
        rows.append({
            "run": config["run"], "variant": config["variant"],
            "imgsz": config["imgsz"], "status": "ok", **stats,
            "temp_before_c": None if before is None else round(before, 1),
            "temp_after_c": None if after is None else round(after, 1),
            "throttled": throttled_flags(), "frame": frame_label,
        })
        print(f"    {stats['fps']} FPS   ({stats['total_ms']} ms total, "
              f"{stats['inference_ms']} ms inference)"
              f"{'' if after is None else f'   {after:.1f} C'}")

    ok = [r for r in rows if r.get("status") == "ok"]
    print(f"\n{'run':16s} {'variant':10s} {'imgsz':>5s} {'infer':>8s} {'total':>8s} "
          f"{'FPS':>6s}  {TARGET_FPS}+FPS?")
    print("-" * 68)
    for row in sorted(ok, key=lambda r: -r["fps"]):
        meets = "yes" if row["fps"] >= TARGET_FPS else "no"
        print(f"{row['run']:16s} {row['variant']:10s} {row['imgsz']:5d} "
              f"{row['inference_ms']:7.1f}m {row['total_ms']:7.1f}m "
              f"{row['fps']:6.1f}  {meets}")

    if rows:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fields = sorted({key for row in rows for key in row})
        with args.out.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {args.out}")

    end_temp = soc_temp_c()
    if end_temp is not None:
        print(f"SoC temp at end: {end_temp:.1f} C   throttled: {throttled_flags()}")
        print("(throttled != 0x0 means the numbers above are thermally limited)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
