"""Traffic-sign detector — per-frame sign bounding boxes.

Object-detection front end for the signs pipeline (YOLO-class model; see the
benchmarking groundwork in ``experiments/object_detection/``). Emits raw
detections that ``tracker.py`` stabilises across frames and ``classes.py``
maps to sign meanings.

TODO: implement. Return a list of detections (bbox, class id, score).
"""
from __future__ import annotations

from typing import List

import numpy as np  # type: ignore


def detect(frame: "np.ndarray") -> "List[dict]":
    """Detect traffic signs in a BGR frame."""
    raise NotImplementedError("TODO: sign detector")
