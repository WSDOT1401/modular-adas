"""Benchmark YOLO26n across export formats on a Raspberry Pi 5 (ARM CPU)."""

import time
import numpy as np
import pandas as pd
from ultralytics import YOLO

MODEL = "yolo26n.pt"          # note: 'yolo26n.pt', not 'yolo26nano.pt'
IMGSZ = 640
WARMUP, RUNS = 5, 50
TARGET_FPS = 18               # lower bound of the 18-25 FPS goal

# label -> ultralytics export format ("pt" = native PyTorch, no export)
FORMATS = {
    "PyTorch":    "pt",
    "ONNX":       "onnx",
    "NCNN":       "ncnn",
    "OpenVINO":   "openvino",
    "ExecuTorch": "executorch",
}


def measure(weights):
    """Return (mean inference ms, mean total-pipeline ms) on a fixed 640x640 frame."""
    model = YOLO(weights)
    frame = np.zeros((IMGSZ, IMGSZ, 3), dtype=np.uint8)

    for _ in range(WARMUP):
        model.predict(frame, imgsz=IMGSZ, verbose=False)

    infer, total = [], []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        r = model.predict(frame, imgsz=IMGSZ, verbose=False)[0]
        total.append((time.perf_counter() - t0) * 1000)
        infer.append(r.speed["inference"])          # raw inference only
    return float(np.mean(infer)), float(np.mean(total))


rows = []
for name, fmt in FORMATS.items():
    try:
        weights = MODEL if fmt == "pt" else YOLO(MODEL).export(format=fmt, imgsz=IMGSZ)
        infer_ms, total_ms = measure(weights)
        fps = 1000 / total_ms
        rows.append({
            "Format": name,
            "Status": "ok",
            "Infer (ms)": round(infer_ms, 1),
            "Total (ms)": round(total_ms, 1),
            "FPS": round(fps, 1),
            "Meets target": "yes" if fps >= TARGET_FPS else "no",
        })
    except Exception as e:
        rows.append({"Format": name, "Status": f"fail: {type(e).__name__}",
                     "Infer (ms)": None, "Total (ms)": None, "FPS": None,
                     "Meets target": "-"})

df = pd.DataFrame(rows)
print("\nYOLO26n @ {}x{}  (Raspberry Pi 5, FP32)\n".format(IMGSZ, IMGSZ))
print(df.to_string(index=False))
df.to_csv("yolo26n_benchmark.csv", index=False)