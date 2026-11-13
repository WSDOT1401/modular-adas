"""Sign tracker — one announcement per physical sign, not one per frame.

A sign stays in view for 10–30 frames as you approach it, and b01 finds it in
only about one frame in three. So: a class counts as seen once it has turned
up in ``confirm_frames`` frames, with gaps allowed; it fires once; and it
rearms only after it has been absent for ``gap_frames`` frames in a row (the
sign has gone by). The same idea as ``SignVote`` in the speed reader, per
class.

A class that has fired also stays quiet for ``repeat_s`` seconds whatever the
gap. Stopped at a light, a distant sign flickers in and out of b01's view for
as long as the car waits; without this it was announced every few seconds
(found on the dashcam clip: one pedestrian crossing sign, 12 times).

ponytail: no IoU tracking. Two of the same sign in view at once count as one,
which is what the driver needs anyway.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Iterable, List


class SignTracker:
    def __init__(self, confirm_frames: int = 3, gap_frames: int = 12,
                 repeat_s: float = 0.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.confirm_frames = confirm_frames
        self.gap_frames = gap_frames
        self.repeat_s = repeat_s
        self._clock = clock
        self._hits: Dict[str, int] = {}
        self._idle: Dict[str, int] = {}
        self._fired: set = set()
        self._last: Dict[str, float] = {}     # class -> when it last fired

    def update(self, names: Iterable[str]) -> "List[str]":
        """Advance one frame with the classes detected in it; return the ones
        confirmed this frame (each physical sign exactly once)."""
        present = list(dict.fromkeys(names))      # de-duplicate, keep order
        confirmed = []
        now = self._clock()
        for name in present:
            self._hits[name] = self._hits.get(name, 0) + 1
            self._idle[name] = 0
            if self._hits[name] >= self.confirm_frames and name not in self._fired:
                self._fired.add(name)
                last = self._last.get(name)
                if last is None or now - last >= self.repeat_s:
                    self._last[name] = now
                    confirmed.append(name)
        for name in list(self._idle):
            if name in present:
                continue
            self._idle[name] += 1
            if self._idle[name] > self.gap_frames:    # the sign has gone by: rearm
                del self._idle[name]
                self._hits.pop(name, None)
                self._fired.discard(name)
        return confirmed
