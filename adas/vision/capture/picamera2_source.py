"""Picamera2 frame source — CSI Camera Module 3 on the Pi.

The on-vehicle backend for ``base.FrameSource`` when ``config.SOURCE == "camera"``.

TODO: implement. Configure Picamera2 for ``config.FRAME_WIDTH`` x
``config.FRAME_HEIGHT`` at ``config.TARGET_FPS`` and yield BGR frames.
Pi-only dependency (``picamera2``); keep the import lazy so off-Pi development
against the file-replay backend never needs it.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np  # type: ignore


def frames(width: int, height: int, target_fps: int) -> Iterator["np.ndarray"]:
    """Yield BGR frames from the CSI camera until stopped."""
    raise NotImplementedError("TODO: Picamera2 capture backend")
