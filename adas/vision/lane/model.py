"""Learned lane model — optional ML alternative to the classical detector.

``detector.py`` starts with classical Hough-based lane finding; this module is
the seam for a learned lane-segmentation model (e.g. a small CNN) that produces
the same signed lateral offset ``departure.DepartureDecider`` consumes, so the
two are interchangeable without touching the decision logic.

TODO: implement (load weights via a ``models/manifests/`` entry; run inference;
return a signed offset). Not required for the classical-CV path.
"""
from __future__ import annotations

from typing import Optional

import numpy as np  # type: ignore


class LaneModel:
    def __init__(self, weights: Optional[str] = None) -> None:
        self._weights = weights

    def lane_offset(self, frame: "np.ndarray") -> Optional[float]:
        """Signed lateral offset from lane center (see ``detector.lane_offset``)."""
        raise NotImplementedError("TODO: learned lane-offset model")
