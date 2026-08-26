"""Playground: monocular distance via ground-plane geometry (no depth network).

Real-time display version: shows each frame as it's processed instead of saving.
Press 'q' or close the window to quit.

You MUST set CAM_HEIGHT, PITCH_DEG and HFOV_DEG for YOUR dashcam.

pip install ultralytics opencv-python
"""

import math
import time
import cv2
from ultralytics import YOLO

# --- camera setup: MEASURE / CALIBRATE THESE for your dashcam ---
CAM_HEIGHT = 1.15        # metres: lens height above the road
PITCH_DEG  = -0.5        # downward tilt; 0 = optical axis horizontal
HFOV_DEG   = 140.0       # horizontal field of view (from the dashcam's spec sheet)

DET_MODEL = "yolo26n.pt"
VIDEO_IN  = "experiments/distance_estimation/dash2.mp4"   # or 0 for a live webcam
ROAD_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle", "person"}

detector = YOLO(DET_MODEL)


def ground_distance(v, fy, cy, pitch):
    """Forward distance (m) to the road point imaged at row v; None if above horizon."""
    depression = pitch + math.atan2(v - cy, fy)   # angle below horizontal
    if depression <= 1e-3:                          # at/above horizon -> no ground hit
        return None
    return CAM_HEIGHT / math.tan(depression)


cap = cv2.VideoCapture(VIDEO_IN)
if not cap.isOpened():
    raise FileNotFoundError(f"Couldn't open {VIDEO_IN!r}")

W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

fx = (W / 2) / math.tan(math.radians(HFOV_DEG) / 2)   # focal length in pixels from FOV
fy, cx, cy = fx, W / 2, H / 2
pitch = math.radians(PITCH_DEG)

WINDOW = "distance (press q to quit)"
cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
fps_smooth = 0.0

while True:
    ok, frame = cap.read()
    if not ok:
        break

    t0 = time.perf_counter()
    for box in detector(frame, verbose=False)[0].boxes:
        label = detector.names[int(box.cls)]
        if label not in ROAD_CLASSES:
            continue
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        u, v = (x1 + x2) / 2, y2                 # bottom-centre = road contact point
        Z = ground_distance(v, fy, cy, pitch)
        if Z is None:
            continue
        X = Z * (u - cx) / fx                    # lateral offset
        rng = math.hypot(X, Z)                   # straight-line distance
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"{label} {rng:.1f}m", (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # live processing FPS (exponentially smoothed)
    dt = time.perf_counter() - t0
    if dt > 0:
        fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt)
    cv2.putText(frame, f"{fps_smooth:4.1f} FPS", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    cv2.imshow(WINDOW, frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):        # quit on 'q'
        break
    if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:   # or window closed
        break

cap.release()
cv2.destroyAllWindows()