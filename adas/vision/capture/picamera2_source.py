"""Picamera2 frame source: the CSI Camera Module 3 (IMX708) on the Pi.

The on-vehicle backend for ``base.FrameSource`` when ``config.SOURCE == "camera"``.

The IMX708 has three sensor modes:

  ===========  ===========  =======================================
  4608x2592    up to 14 fps  full resolution (the default)
  2304x1296    up to 56 fps  full view, 2x2 binned (main.py --camera binned)
  1536x864     up to 120 fps  cropped to the middle
  ===========  ===========  =======================================

Picamera2 picks the mode closest to the requested size. The sign detector
works at 1280 wide either way; the extra pixels only help the speed reader,
which crops the sign out of the full frame. Full resolution doubles the
pixels across each sign; binned keeps 30 fps, so a sign stays in view for
twice as many frames.

Focus is fixed at infinity (``lens_position=0.0``; None for autofocus): from behind a
windscreen, autofocus hunts on the glass, wipers and rain.

Frames come out BGR, as OpenCV expects (Picamera2's "RGB888" is B, G, R in
memory). Pi-only dependency (``picamera2``); the import stays lazy so
off-Pi development against the file-replay backend never needs it.
"""
from __future__ import annotations

from typing import Iterator, Optional

import numpy as np  # type: ignore


def frames(width: int, height: int, target_fps: int,
           lens_position: Optional[float] = 0.0) -> Iterator["np.ndarray"]:
    """Yield BGR frames from the CSI camera until stopped."""
    from picamera2 import Picamera2  # type: ignore
    from libcamera import controls  # type: ignore

    cam = Picamera2()
    ctrl = {"FrameRate": float(target_fps)}
    if lens_position is None:
        ctrl["AfMode"] = controls.AfModeEnum.Continuous
    elif "LensPosition" in cam.camera_controls:      # Camera Module 3 (fixed-focus modules have none)
        ctrl.update(AfMode=controls.AfModeEnum.Manual, LensPosition=float(lens_position))
    cam.configure(cam.create_video_configuration(
        main={"size": (width, height), "format": "RGB888"},
        sensor={"output_size": (width, height)},
        controls=ctrl, buffer_count=4))
    cam.start()
    try:
        while True:
            yield cam.capture_array("main")
    finally:
        cam.stop()
        cam.close()
