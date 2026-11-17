"""Speed reader — the number on a speed_limit sign.

The reader (``speed_reader.pt``, MobileNetV3-Small) and its vote live in
``classify.py`` next to its training code in
``adas/experiments/traffic-sign_recognition/speed_limit_classifier/``. That
file is deliberately not copied here (one copy, no drift), so it is imported
from wherever ``config.SPEED_READER_CODE`` points. On the Pi, copy
``classify.py`` alongside the two ``.pt`` files and point the config at it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple


def load_reader(ckpt: str, code_dir: str, device: str = "cpu") -> Tuple[object, object]:
    """Return ``(reader, vote)``: ``reader(frame, box) -> (value | None, conf)``
    and ``vote.update(value | None) -> value once per sign | None``."""
    code = str(Path(code_dir).resolve())
    if code not in sys.path:
        sys.path.insert(0, code)
    from classify import SignVote, SpeedClassifier  # type: ignore

    return SpeedClassifier(ckpt=ckpt, device=device), SignVote()
