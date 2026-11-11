"""Video-replay frame source — replay a recorded clip via OpenCV.

The off-Pi development backend for ``base.FrameSource`` when
``config.SOURCE == "file"``. Reads ``config.CLIP_PATH`` (record fresh clips with
``tools/record_clip.py``; keep fixtures under ``tests/fixtures/``).

TODO: implement. Open the clip with ``cv2.VideoCapture`` and yield BGR frames,
optionally throttled to ``config.TARGET_FPS``.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np  # type: ignore


def frames(clip_path: str, target_fps: int) -> Iterator["np.ndarray"]:
    """Yield BGR frames decoded from ``clip_path`` until the clip is exhausted."""
    raise NotImplementedError("TODO: OpenCV file-replay backend")
