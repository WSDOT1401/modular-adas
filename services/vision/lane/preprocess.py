"""Frame preprocessing: ROI masking and edge extraction — the front half of
the classical-CV lane pipeline.

TODO: implement. Suggested order (per research — Cornell ECE5725, JunshengFu):
  grayscale -> Gaussian blur -> Canny edges -> ROI mask -> (optional) warp.
"""
from __future__ import annotations

import numpy as np  # type: ignore

import config


def region_of_interest(frame: "np.ndarray") -> "np.ndarray":
    """Mask out everything above ``config.ROI_TOP``."""
    raise NotImplementedError("TODO")


def edges(frame: "np.ndarray") -> "np.ndarray":
    """Grayscale -> blur -> Canny, using ``config`` thresholds."""
    raise NotImplementedError("TODO")
