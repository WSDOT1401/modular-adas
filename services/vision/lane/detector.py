"""Lane-line detection: from an edge image to a signed lateral offset of the
vehicle from lane center.

Two viable approaches (see research):
  - Hough lines: pick dominant left/right slopes, intersect with a baseline.
  - Bird's-eye + sliding window + polyfit: more robust, heavier.
Start with Hough; you can swap in the warp/polyfit method later without
touching departure.py (it only consumes the offset).

TODO: implement. Return the signed offset, or None if no lane was found.
"""
from __future__ import annotations

from typing import Optional

import numpy as np  # type: ignore

import config  # noqa: F401  (thresholds used once implemented)


def lane_offset(edge_frame: "np.ndarray") -> Optional[float]:
    """Estimate signed lateral offset from lane center.

    Negative = drifting left, positive = drifting right; magnitude in
    fractions of a half-lane (1.0 == wheel on the marking). None when no lane
    is detected this frame.
    """
    raise NotImplementedError("TODO: Hough-based lane offset")
