"""Signs stage: frame -> detections -> once-per-sign events -> protocol keys.

    frame ──► detector ──► publishable boxes ──► tracker ──► sign_seen
                               └─ speed_limit box ─► reader ─► vote ─► speed_limit

What reaches the display (``adas_protocol`` keys):

  - a new sign of any class but speed_limit:  ``sign_seen: "<class>"``
  - a speed_limit sign, confirmed:             ``sign_seen: "speed_limit"``
    (the display rings the limit sign at once, before the number is read)
  - its number, once the vote settles:         ``speed_limit: 80`` plus
    ``sign_seen: "speed_limit"`` again
  - an unreadable number: nothing more; the old limit stays.

One ``sign_seen`` per datagram: if two new signs confirm in the same frame,
the second goes out with the next frame.
"""
from __future__ import annotations

from collections import deque
from typing import List, Optional, Tuple

from adas_protocol import SIGN_SEEN, SPEED_LIMIT as SPEED_LIMIT_KEY

from signs.classes import SPEED_LIMIT, publishable
from signs.tracker import SignTracker


class SignPipeline:
    def __init__(self, detector, reader=None, vote=None,
                 tracker: Optional[SignTracker] = None) -> None:
        self._detector = detector
        self._reader = reader            # None: limits are announced without a number
        self._vote = vote
        self._tracker = tracker or SignTracker()
        self._pending: deque = deque()

    def update(self, frame) -> "Tuple[dict, List[dict]]":
        """Process one frame. Returns ``(keys to publish, detections)``; the
        detections are for drawing a preview."""
        detections = [d for d in self._detector.detect(frame) if publishable(d["name"])]
        out: dict = {}

        for name in self._tracker.update(d["name"] for d in detections):
            self._pending.append(name)

        if self._reader is not None and self._vote is not None:
            limits = [d for d in detections if d["name"] == SPEED_LIMIT]
            value = None
            if limits:
                # The biggest box is the nearest sign, with the most readable digits.
                nearest = max(limits, key=lambda d: d["box"][2] - d["box"][0])
                value, _conf = self._reader(frame, nearest["box"])
            settled = self._vote.update(value)    # once per frame, None included
            if settled:
                out[SPEED_LIMIT_KEY] = int(settled)
                out[SIGN_SEEN] = SPEED_LIMIT

        if SIGN_SEEN not in out and self._pending:
            out[SIGN_SEEN] = self._pending.popleft()
        return out, detections
