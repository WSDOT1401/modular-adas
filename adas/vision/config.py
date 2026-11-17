"""Lane-departure module configuration — all tunables in one place.

Mirrors the constants-at-top convention of the VSS reader. Per-vehicle values
(camera mount, windshield rake) ultimately belong in config/<vehicle>.toml at
the repo root; these are sane defaults for bench work.
"""
from __future__ import annotations

import importlib.util
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
# Camera Module 3 (IMX708): its full resolution, 4608x2592, runs at 14 fps.
# main.py --camera binned: 2304x1296 at 30 fps, same view, half the pixels
# on each sign (see capture/picamera2_source.py).
FRAME_WIDTH = 4608
FRAME_HEIGHT = 2592
TARGET_FPS = 14
CAMERA_MODES = {"full": (4608, 2592, 14), "binned": (2304, 1296, 30)}

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
# On a Pi with an AI HAT, b01 runs on the Hailo chip: tools/export_hailo.py
# compiles it into central/b01_hailo_model/, used whenever that folder is
# there and the Hailo runtime is installed (the AI HAT is fitted). Otherwise
# b01.pt runs on the CPU, so a PC with a copy of the folder still works.
_HAILO_SIGNS = _ADAS / "experiments/central/b01_hailo_model"
_HAS_HAILO = importlib.util.find_spec("hailo_platform") is not None
SIGN_WEIGHTS = str(_HAILO_SIGNS if _HAILO_SIGNS.is_dir() and _HAS_HAILO
                   else _ADAS / "experiments/central/b01.pt")
SPEED_READER = str(_ADAS / "experiments/central/speed_reader.pt")
# classify.py, which loads speed_reader.pt; on the Pi, copy it next to the .pt files.
SPEED_READER_CODE = str(_ADAS / "experiments/traffic-sign_recognition/speed_limit_classifier")
SIGN_IMGSZ = 1280              # b01 was trained at 1280; at 640 small signs vanish
# INT8 on the Hailo scores signs a little lower than b01.pt does (the 30 km/h
# sign at 0:31 of the bench clip: 0.46-0.63 vs the .pt's higher scores).
SIGN_CONF = 0.4 if SIGN_WEIGHTS.endswith("_hailo_model") else 0.5
SIGN_DEVICE = None             # None = ultralytics picks; "cpu", "0" (CUDA), "mps" (Mac)
# Frames in flight on the AI HAT: 1 = 18 fps, 2 = 35, 3+ = ~60 (the chip's
# limit). Detections arrive this many frames late (100 ms at 30 fps).
SIGN_HAILO_DEPTH = 3
# A sign counts after this many frames with it (gaps allowed), and rearms after
# this many frames without it. The same class is not announced again within
# SIGN_REPEAT_S seconds (a car waiting at a light keeps seeing the same sign).
SIGN_CONFIRM_FRAMES = 3
SIGN_GAP_FRAMES = 12
SIGN_REPEAT_S = 20.0

# --- sign_v3 (central/sign_v3): M1 finds the sign, M2 names it -------------------
# The default whenever its m1.pt is there; main.py --signs b01 for the old
# single model. Each model runs on the AI HAT once compiled
# (tools/export_hailo.py for M1, tools/export_m2_hailo.py for M2) and the
# Hailo runtime is installed; otherwise through PyTorch.
_V3 = _ADAS / "experiments/central/sign_v3"
SIGN_STACK = "v3" if (_V3 / "m1.pt").is_file() else "b01"       # "v3" | "b01"


def _v3(name: str) -> str:
    hailo = _V3 / f"{name}_hailo_model"
    return str(hailo if hailo.is_dir() and _HAS_HAILO else _V3 / f"{name}.pt")


V3_M1 = _v3("m1")
V3_M2 = _v3("m2")
# M1 only says "a sign is here"; M2 (with its not_a_sign class) throws out
# the mistakes, so M1 runs at run.py's low threshold.
V3_M1_CONF = 0.25

# --- Output (shared UDP contract) ------------------------------------------
# None: adas_protocol's default, 127.0.0.1:9100, or ADAS_UDP_TARGETS if set.
UDP_HOST = None
UDP_PORT = None
# Where the display's feature on/off choices arrive. None: adas_protocol's
# DEFAULT_CONTROL_PORT (9102).
CONTROL_PORT = None
# Interface the control port listens on: this machine only, unless the
# display is on another one (main.py --display sets "0.0.0.0").
CONTROL_BIND = "127.0.0.1"

# --- Sharing the Pi with the display (runtime/priority.py) -------------------
# The driver's display must stay smooth while the models run: the vision
# service and the stats window keep off these cores, which the display, the
# desktop and X then always find free, and run this much lower in priority
# (nice; 0-19, higher = yields more). main.py --all-cores turns it off.
DISPLAY_CORES = (3,)           # the Pi 5's last core; core 0 also takes most interrupts
VISION_NICE = 10

# --- Stats screen (tools/stats_window.py, never the driver's display) -------
# The frame with its boxes goes to the stats window this many times a second,
# and only while it is open.
PREVIEW_FPS = 15
