"""Video-replay frame source — replay a recorded clip via OpenCV.

The off-Pi development backend for ``base.FrameSource`` when
``config.SOURCE == "file"``: a dashcam clip stands in for the camera.

Frames come out at their native resolution (the sign detector resizes for
itself, and the speed reader crops from the full-resolution frame).

``realtime=True`` (the default) replays at the clip's own pace, like a camera:
if the pipeline is slower than the clip, frames are dropped to stay on time,
the way a live camera would drop them. ``realtime=False`` processes every
frame, as fast as the pipeline can go (slower or faster than real time).
"""
from __future__ import annotations

import time
from typing import Iterator

import numpy as np  # type: ignore


class VideoReplaySource:
    def __init__(self, clip_path: str, realtime: bool = True, loop: bool = False) -> None:
        import cv2  # type: ignore  (lazy: tests and the Pi camera path never need it)

        self._cv2 = cv2
        self._path = clip_path
        self._realtime = realtime
        self._loop = loop
        self._cap = cv2.VideoCapture(clip_path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"cannot open clip {clip_path!r}")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 1 else 30.0
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.time = 0.0        # clip time of the last frame handed out, s
        self.dropped = 0       # frames skipped to keep up (realtime only)

    def frames(self) -> Iterator["np.ndarray"]:
        """Yield BGR frames until the clip ends (or forever with ``loop``)."""
        while True:
            yield from self._play_once()
            if not self._loop:
                return
            self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)

    def _play_once(self) -> Iterator["np.ndarray"]:
        start = time.monotonic()
        index = 0
        while True:
            if self._realtime:
                due = index / self.fps
                behind = time.monotonic() - start - due
                # Skip whole frames we are already late for (grab() doesn't decode).
                while behind > 1.0 / self.fps:
                    if not self._cap.grab():
                        return
                    index += 1
                    self.dropped += 1
                    behind -= 1.0 / self.fps
                ahead = index / self.fps - (time.monotonic() - start)
                if ahead > 0:
                    time.sleep(ahead)
            ok, frame = self._cap.read()
            if not ok:
                return
            self.time = index / self.fps
            index += 1
            yield frame

    def close(self) -> None:
        self._cap.release()


def frames(clip_path: str, realtime: bool = True) -> Iterator["np.ndarray"]:
    """Yield BGR frames decoded from ``clip_path`` until the clip is exhausted."""
    source = VideoReplaySource(clip_path, realtime=realtime)
    try:
        yield from source.frames()
    finally:
        source.close()


__all__ = ["VideoReplaySource", "frames"]
