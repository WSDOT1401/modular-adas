"""Departure decision: turn a per-frame lane-offset estimate into a stable
warning state + direction, with hysteresis so noise doesn't flicker the alert.

Pure logic — no camera, no OpenCV — so it is fully unit-testable off the Pi
(see tests/test_departure.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from w124_protocol import LANE_WARNING, LANE_DIRECTION, LANE_CONFIDENCE


@dataclass
class Decision:
    active: bool
    direction: str        # "left" | "right" | "none"
    confidence: float

    def to_payload(self) -> dict:
        """Render as the snake_case UDP contract fragment."""
        return {
            LANE_WARNING: self.active,
            LANE_DIRECTION: self.direction,
            LANE_CONFIDENCE: round(self.confidence, 2),
        }


class DepartureDecider:
    """Debounced lane-departure state machine.

    Feed it a signed lateral offset each frame (negative = drifting left,
    positive = drifting right; magnitude in fractions of a half-lane, where
    1.0 means the wheel is on the marking). It raises a warning only after
    ``raise_frames`` consecutive over-threshold frames, and clears only after
    ``clear_frames`` consecutive safe frames.
    """

    def __init__(self, depart_offset: float, raise_frames: int, clear_frames: int) -> None:
        self._threshold = depart_offset
        self._raise_frames = raise_frames
        self._clear_frames = clear_frames
        self._over = 0
        self._under = 0
        self._active = False
        self._direction = "none"

    def update(self, offset: Optional[float], confidence: float = 1.0) -> Decision:
        # offset is None when no lane could be detected this frame -> treat as safe.
        drifting = offset is not None and abs(offset) >= self._threshold
        if drifting:
            self._over += 1
            self._under = 0
            if self._over >= self._raise_frames:
                self._active = True
                self._direction = "left" if offset < 0 else "right"
        else:
            self._under += 1
            self._over = 0
            if self._under >= self._clear_frames:
                self._active = False
                self._direction = "none"

        return Decision(
            active=self._active,
            direction=self._direction,
            confidence=confidence if self._active else 0.0,
        )
