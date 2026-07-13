"""Lane-departure module configuration — all tunables in one place.

Mirrors the constants-at-top convention of the VSS reader. Per-vehicle values
(camera mount, windshield rake) ultimately belong in config/<vehicle>.toml at
the repo root; these are sane defaults for bench work.
"""
from __future__ import annotations

# --- Frame source ----------------------------------------------------------
SOURCE = "camera"              # "camera" (Picamera2) | "file" (replay a clip)
CLIP_PATH = "samples/sample_drive.mp4"   # used when SOURCE == "file"
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 15

# --- Region of interest / perspective (calibrate per vehicle) --------------
ROI_TOP = 0.55                 # ignore everything above this fraction of height
WARP_SRC = None                # 4 perspective points (px); set via tools/calibrate.py

# --- Lane detection (classical CV) -----------------------------------------
CANNY_LOW = 50
CANNY_HIGH = 150
HOUGH_THRESHOLD = 40
HOUGH_MIN_LINE = 40
HOUGH_MAX_GAP = 100

# --- Departure decision ----------------------------------------------------
# Signed lateral offset from lane center, in fractions of a half-lane width
# (0 = centered, 1 = wheel on the marking), beyond which we count as drifting.
DEPART_OFFSET = 0.75
# Hysteresis: consecutive frames required to raise / clear the warning, so a
# single noisy frame never flickers the alert.
RAISE_FRAMES = 3
CLEAR_FRAMES = 5

# --- Output (shared UDP contract) ------------------------------------------
UDP_HOST = "127.0.0.1"
UDP_PORT = 9100
