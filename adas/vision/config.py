"""Lane-departure module configuration — all tunables in one place.

Mirrors the constants-at-top convention of the VSS reader. Per-vehicle values
(camera mount, windshield rake) ultimately belong in config/<vehicle>.toml at
the repo root; these are sane defaults for bench work.
"""
from __future__ import annotations

from pathlib import Path

_ADAS = Path(__file__).resolve().parent.parent      # adas/

# --- Which stages run -------------------------------------------------------
# Lane joins once its CV stages (lane/preprocess, lane/detector) are written;
# until then the display shows lane departure as switched off.
STAGES = ("signs",)            # any of "signs", "lane"

# --- Frame source ----------------------------------------------------------
SOURCE = "camera"              # "camera" (Picamera2) | "file" (replay a clip)
CLIP_PATH = "tests/fixtures/sample_drive.mp4"   # used when SOURCE == "file"
REPLAY_REALTIME = True         # file: keep the clip's pace, dropping frames like a camera would
REPLAY_LOOP = False            # file: start again at the end
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

# --- Traffic signs (adas/experiments/central: the two models that ship) ------
# The .pt files are gitignored: copy them in by hand (see that folder's README).
SIGN_WEIGHTS = str(_ADAS / "experiments/central/b01.pt")
SPEED_READER = str(_ADAS / "experiments/central/speed_reader.pt")
# classify.py, which loads speed_reader.pt; on the Pi, copy it next to the .pt files.
SPEED_READER_CODE = str(_ADAS / "experiments/traffic-sign_recognition/speed_limit_classifier")
SIGN_IMGSZ = 1280              # b01 was trained at 1280; at 640 small signs vanish
SIGN_CONF = 0.5
SIGN_DEVICE = None             # None = ultralytics picks; "cpu", "0" (CUDA), "mps" (Mac)
# A sign counts after this many frames with it (gaps allowed), and rearms after
# this many frames without it.
SIGN_CONFIRM_FRAMES = 3
SIGN_GAP_FRAMES = 12

# --- Output (shared UDP contract) ------------------------------------------
# None: adas_protocol's default, 127.0.0.1:9100, or ADAS_UDP_TARGETS if set.
UDP_HOST = None
UDP_PORT = None
