"""Traffic-sign detector — per-frame sign boxes from the b01 YOLO model.

b01 (``adas/experiments/central/b01.pt``) finds a sign and names its class in
one pass. Run it at ``imgsz=1280``: it was trained there, and at the
ultralytics default of 640 small signs simply vanish.

Each detection is a dict: ``{"name": str, "box": (x0, y0, x1, y1), "score":
float}`` with the box in the frame's own pixels.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np  # type: ignore


class SignDetector:
    def __init__(self, weights: str, imgsz: int = 1280, conf: float = 0.5,
                 device: Optional[str] = None) -> None:
        from ultralytics import YOLO  # type: ignore  (lazy: heavy, and tests don't need it)

        self._model = YOLO(weights)
        self._imgsz = imgsz
        self._conf = conf
        self._device = device

    def detect(self, frame: "np.ndarray") -> "List[dict]":
        """Detect traffic signs in a BGR frame."""
        kwargs = {"imgsz": self._imgsz, "conf": self._conf, "verbose": False}
        if self._device:
            kwargs["device"] = self._device
        result = self._model.predict(frame, **kwargs)[0]
        names = result.names
        boxes = result.boxes
        return [
            {"name": names[int(c)], "box": tuple(float(v) for v in xyxy), "score": float(s)}
            for c, xyxy, s in zip(boxes.cls.tolist(), boxes.xyxy.tolist(), boxes.conf.tolist())
        ]
