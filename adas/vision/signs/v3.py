"""sign_v3: M1 finds the signs, M2 names them (adas/experiments/central/sign_v3).

    frame ──► M1 (one class, "sign", @1280) ──► boxes ──► square 128 px crop ──► M2 ──► name

M1 doesn't know which sign; M2 does, from a crop, and has a ``not_a_sign``
class for M1's mistakes. Only the classes M2 lists as ``displayed`` (13 of
its 29) come out of here; the rest are real signs the dash stays quiet about.

The crop is the contract between M2's training and this code, and getting it
wrong fails silently (M2 still answers, just worse), so it is
``sign_v3/run.py``'s, unchanged: nothing under 24 source px on the short
side, squared around the box centre, clamped to the frame, resized with
Lanczos. :func:`square_crop` cuts the square out of the frame first and
resizes only that, which gives the same pixels as cropping a PIL image of the
whole frame without converting a 12 MP frame every time.

Either model runs on the AI HAT (signs/hailo10.py) or through PyTorch
(:class:`TorchCropClassifier`, and signs/detector.py for M1).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np  # type: ignore

READABLE = 24       # source px, short side: the smallest crop M2 was trained on
NOT_A_SIGN = "not_a_sign"


def square_crop(frame: "np.ndarray", box, size: int) -> "np.ndarray":
    """BGR frame + box -> size x size RGB crop, as sign_v3/run.py's square()."""
    from PIL import Image  # type: ignore

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    half = min(max(x2 - x1, y2 - y1) / 2, w / 2, h / 2)
    cx = min(max((x1 + x2) / 2, half), w - half)
    cy = min(max((y1 + y2) / 2, half), h - half)
    l, t, r, b = round(cx - half), round(cy - half), round(cx + half), round(cy + half)
    crop = np.ascontiguousarray(frame[max(t, 0):b, max(l, 0):r, ::-1])      # BGR -> RGB
    return np.asarray(Image.fromarray(crop).resize((size, size), Image.LANCZOS))


class TorchCropClassifier:
    """M2 from m2.pt through PyTorch (no AI HAT, e.g. on a PC)."""

    on_hailo = False

    def __init__(self, path: str, device: Optional[str] = None) -> None:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        from torchvision.models import mobilenet_v3_small  # type: ignore

        self._torch = torch
        self._device = device or ("cuda" if torch.cuda.is_available() else
                                  "mps" if torch.backends.mps.is_available() else "cpu")
        ck = torch.load(path, weights_only=False, map_location=self._device)
        net = mobilenet_v3_small()
        net.classifier[3] = nn.Linear(1024, len(ck["classes"]))
        net.load_state_dict(ck["state_dict"])
        self._net = net.to(self._device).eval()
        self.classes: List[str] = list(ck["classes"])
        self.displayed = set(ck["displayed"])
        self.size = int(ck["size"])
        # ImageNet: M2 starts from ImageNet weights (as run.py's NORM).
        self._mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        self._std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

    def classify(self, crops: "List[np.ndarray]") -> "List[Tuple[str, float]]":
        if not crops:
            return []
        torch = self._torch
        x = torch.from_numpy(np.stack(crops)).permute(0, 3, 1, 2).float() / 255.0
        x = ((x - self._mean) / self._std).to(self._device)
        with torch.no_grad():
            conf, idx = self._net(x).softmax(1).max(1)
        return [(self.classes[int(j)], float(c)) for c, j in zip(conf.tolist(), idx.tolist())]

    def close(self) -> None:
        pass


class V3Detector:
    """M1 + M2 behind the interface signs/pipeline.py expects of a detector.

    With M1 on the AI HAT it is pipelined like b01 there (``push`` answers
    for a frame a few calls back and hands that frame over); otherwise
    ``push`` is plain detect-and-return. Detections: ``{"name", "box",
    "score"}``, score being M2's confidence."""

    def __init__(self, m1, m2) -> None:
        self._m1, self._m2 = m1, m2
        self.on_hailo = bool(getattr(m1, "on_hailo", False))
        self.m2_on_hailo = bool(getattr(m2, "on_hailo", False))
        self.displayed = set(m2.displayed) - {NOT_A_SIGN}

    @property
    def stats(self) -> dict:
        return getattr(self._m1, "stats", {})

    def push(self, frame: "np.ndarray") -> "Optional[Tuple[np.ndarray, List[dict]]]":
        if hasattr(self._m1, "push"):
            done = self._m1.push(frame)
            if done is None:
                return None
            frame, boxes = done
        else:
            boxes = self._m1.detect(frame)
        return frame, self._name(frame, boxes)

    def detect(self, frame: "np.ndarray") -> "List[dict]":
        return self._name(frame, self._m1.detect(frame))

    def _name(self, frame: "np.ndarray", boxes: "List[dict]") -> "List[dict]":
        keep = [d for d in boxes
                if min(d["box"][2] - d["box"][0], d["box"][3] - d["box"][1]) >= READABLE]
        if not keep:
            return []
        crops = [square_crop(frame, d["box"], self._m2.size) for d in keep]
        out = []
        for d, (name, conf) in zip(keep, self._m2.classify(crops)):
            if name in self.displayed:
                out.append({"name": name, "box": d["box"], "score": conf})
        return out

    def close(self) -> None:
        for m in (self._m1, self._m2):
            close = getattr(m, "close", None)
            if close is not None:
                close()
