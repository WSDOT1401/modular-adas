"""The vision service's view, for the stats screen (tools/stats_window.py).

A few times a second the frame the signs were found in goes to
:data:`FRAME_FILE` in RAM, shrunk to fit and with the boxes drawn on it.
Like the stats it never reaches the driver's display.

Only while someone watches: the stats window writes the size it wants to
:data:`WANT_FILE` every second, and without a fresh one nothing is drawn or
written, so a Pi with no stats screen spends nothing on this. PPM, because
Tk reads it without any packages and it costs no encoding.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

FRAME_FILE = Path("/dev/shm/adas-frame.ppm")
WANT_FILE = Path("/dev/shm/adas-frame.want")     # "width height", from the stats window
STALE_S = 3.0

BOX = (138, 208, 79)          # BGR of the display's ACTIVE green (#4FD08A)


def wanted() -> Optional[Tuple[int, int]]:
    """The size the stats window asks for, or None when no one is watching."""
    try:
        if time.time() - WANT_FILE.stat().st_mtime > STALE_S:
            return None
        w, h = (int(v) for v in WANT_FILE.read_text().split()[:2])
    except (OSError, ValueError):
        return None
    return (w, h) if 160 <= w <= 3840 and 90 <= h <= 2160 else None


def render(frame, detections: List[dict], size: Tuple[int, int]):
    """The frame fitted inside ``size`` (aspect kept), boxes and names on it."""
    import cv2  # type: ignore

    h, w = frame.shape[:2]
    scale = min(size[0] / w, size[1] / h)
    # A 12 MP frame through INTER_AREA is 19 ms on the Pi, in the vision loop;
    # INTER_LINEAR is 3 ms and only aliases a little: it's a preview.
    view = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))),
                      interpolation=cv2.INTER_LINEAR if scale < 0.5 else cv2.INTER_AREA)
    thick = max(2, round(view.shape[1] / 480))
    for d in detections:
        x0, y0, x1, y1 = (round(v * scale) for v in d["box"])
        cv2.rectangle(view, (x0, y0), (x1, y1), BOX, thick)
        label = f"{d['name']} {d['score']:.2f}"
        font, fs = cv2.FONT_HERSHEY_SIMPLEX, view.shape[1] / 1600
        (tw, th), base = cv2.getTextSize(label, font, fs, thick - 1 or 1)
        ty = y0 - 6 if y0 - th - 10 > 0 else y1 + th + 6
        cv2.rectangle(view, (x0, ty - th - 4), (x0 + tw + 8, ty + base), BOX, -1)
        cv2.putText(view, label, (x0 + 4, ty), font, fs, (5, 6, 5), thick - 1 or 1, cv2.LINE_AA)
    return view


class FramePreview:
    """Writes a frame to FRAME_FILE at most ``fps`` times a second, while wanted."""

    def __init__(self, fps: float = 15.0) -> None:
        self._every = 1.0 / max(fps, 0.1)
        self._last = 0.0
        self._asked_at = 0.0
        self._size: Optional[Tuple[int, int]] = None

    def update(self, frame, detections: List[dict]) -> None:
        now = time.monotonic()
        if now - self._asked_at >= 1.0:                 # look for the window once a second
            self._asked_at = now
            self._size = wanted()
        if self._size is None or frame is None or now - self._last < self._every:
            return
        self._last = now
        import cv2  # type: ignore

        try:
            tmp = FRAME_FILE.with_suffix(".tmp.ppm")
            if cv2.imwrite(str(tmp), render(frame, detections, self._size)):
                os.replace(tmp, FRAME_FILE)            # a reader never sees half a frame
        except OSError:
            pass                                       # no /dev/shm (not Linux): no view

    def close(self) -> None:
        try:
            FRAME_FILE.unlink()
        except OSError:
            pass
