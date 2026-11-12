"""Sign tracker — one announcement per physical sign, not one per frame.

A sign stays in view for 10–30 frames as you approach it, and b01 finds it in
only about one frame in three. So: a class counts as seen once it has turned
up in ``confirm_frames`` frames, with gaps allowed; it fires once; and it
rearms only after it has been absent for ``gap_frames`` frames in a row (the
sign has gone by). The same idea as ``SignVote`` in the speed reader, per
class.

ponytail: no IoU tracking. Two of the same sign in view at once count as one,
which is what the driver needs anyway.
"""
from __future__ import annotations

from typing import Dict, Iterable, List


class SignTracker:
    def __init__(self, confirm_frames: int = 3, gap_frames: int = 12) -> None:
        self.confirm_frames = confirm_frames
        self.gap_frames = gap_frames
        self._hits: Dict[str, int] = {}
        self._idle: Dict[str, int] = {}
        self._fired: set = set()

    def update(self, names: Iterable[str]) -> "List[str]":
        """Advance one frame with the classes detected in it; return the ones
        confirmed this frame (each physical sign exactly once)."""
        present = list(dict.fromkeys(names))      # de-duplicate, keep order
        confirmed = []
        for name in present:
            self._hits[name] = self._hits.get(name, 0) + 1
            self._idle[name] = 0
            if self._hits[name] >= self.confirm_frames and name not in self._fired:
                self._fired.add(name)
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
