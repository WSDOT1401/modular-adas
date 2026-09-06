"""Playground: YOLO26 + Depth Anything V2 (metric) on a video -> annotated video.

pip install ultralytics transformers torch pillow opencv-python
Put a clip next to this file as dash.mp4 and run it.
"""

import cv2
import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

DET_MODEL = "yolo26n.pt"
DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf"  # metres, outdoor
VIDEO_IN = "experiments/distance_estimation/dash2.mp4"
VIDEO_OUT = "experiments/distance_estimation/out.mp4"
STRIDE = 1                       # process every Nth frame; raise to 2-3 to go faster
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"   # M2 GPU

detector = YOLO(DET_MODEL)
processor = AutoImageProcessor.from_pretrained(DEPTH_MODEL)
depth_model = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL).to(DEVICE).eval()


def annotate(bgr):
    """Run both branches on one frame and draw distance-per-object."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    H, W = bgr.shape[:2]

    inputs = processor(images=Image.fromarray(rgb), return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = depth_model(**inputs)
    depth = processor.post_process_depth_estimation(
        out, target_sizes=[(H, W)])[0]["predicted_depth"].cpu().numpy()

    for box in detector(bgr, verbose=False)[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        label = detector.names[int(box.cls)]
        dist = float(np.median(depth[y1:y2, x1:x2]))
        cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(bgr, f"{label} {dist:.1f}m", (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return bgr


cap = cv2.VideoCapture(VIDEO_IN)
if not cap.isOpened():
    raise FileNotFoundError(f"Couldn't open {VIDEO_IN!r}")

fps = (cap.get(cv2.CAP_PROP_FPS) or 30) / STRIDE
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
writer = cv2.VideoWriter(VIDEO_OUT, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

i = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    if i % STRIDE == 0:
        writer.write(annotate(frame))
        print(f"\rframe {i}", end="")
    i += 1

cap.release()
writer.release()
print(f"\nsaved {VIDEO_OUT}")