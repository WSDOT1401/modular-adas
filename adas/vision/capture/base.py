"""Frame acquisition — abstracts the camera so the rest of the pipeline does
not care whether frames come from a Pi camera or a recorded clip.

  - "camera": Picamera2 (CSI Camera Module 3) on the Pi.          (TODO)
  - "file":   replay a recorded clip via OpenCV (off-Pi development).
"""
from __future__ import annotations

from typing import Iterator, Optional

import numpy as np  # type: ignore


class FrameSource:
    def __init__(self, source: str, width: int, height: int,
                 clip_path: Optional[str] = None, realtime: bool = True,
                 loop: bool = False, fps: int = 15) -> None:
        self._source = source
        self._width = width
        self._height = height
        self._clip_path = clip_path
        self._realtime = realtime
        self._loop = loop
        self._fps = fps
        self._replay = None

    @property
    def time(self) -> float:
        """Clip time of the latest frame, s (0 for the live camera)."""
        return self._replay.time if self._replay is not None else 0.0

    @property
    def dropped(self) -> int:
        """Frames dropped to keep up with real time."""
        return self._replay.dropped if self._replay is not None else 0

    def frames(self) -> Iterator["np.ndarray"]:
        """Yield BGR frames until the source is exhausted or stopped."""
        if self._source == "file":
            from capture.video_replay_source import VideoReplaySource
            if not self._clip_path:
                raise ValueError("source 'file' needs a clip path (--clip)")
            self._replay = VideoReplaySource(self._clip_path, self._realtime, self._loop)
            return self._replay.frames()
        if self._source == "camera":
            from capture import picamera2_source
            return picamera2_source.frames(self._width, self._height, self._fps)
        raise ValueError(f"unknown frame source {self._source!r}; use camera or file")

    def close(self) -> None:
        if self._replay is not None:
            self._replay.close()
