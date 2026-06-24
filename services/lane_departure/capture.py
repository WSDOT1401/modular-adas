"""Frame acquisition — abstracts the camera so the rest of the pipeline does
not care whether frames come from a Pi camera or a recorded clip.

  - "camera": Picamera2 (CSI Camera Module 3) on the Pi.
  - "file":   replay a recorded clip via OpenCV (off-Pi development).

TODO: implement the two backends. UI/bench work does not need this — use
tools/mock_lane_writer.py to drive the cluster without any camera.
"""
from __future__ import annotations

from typing import Iterator, Optional

import numpy as np  # type: ignore


class FrameSource:
    def __init__(self, source: str, width: int, height: int,
                 clip_path: Optional[str] = None) -> None:
        self._source = source
        self._width = width
        self._height = height
        self._clip_path = clip_path

    def frames(self) -> Iterator["np.ndarray"]:
        """Yield BGR frames until the source is exhausted or stopped."""
        raise NotImplementedError("TODO: Picamera2 + OpenCV file-replay backends")

    def close(self) -> None:
        pass
