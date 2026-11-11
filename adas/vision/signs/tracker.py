"""Sign tracker — stabilise per-frame detections into persistent tracks.

A single sign should raise one event, not one per frame. This tracks detections
across frames (IoU / centroid association) so a sign is only reported once it is
confirmed over several frames, mirroring the hysteresis idea in
``lane.departure``.

TODO: implement.
"""
from __future__ import annotations

from typing import List


class SignTracker:
    def update(self, detections: "List[dict]") -> "List[dict]":
        """Advance tracks with this frame's detections; return confirmed signs."""
        raise NotImplementedError("TODO: sign tracker")
