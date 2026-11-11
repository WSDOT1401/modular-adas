"""The lab notebook: which frames a human picked, and where they overruled the detector.

``notebook.json`` is tracked in git on purpose -- it records which frames were
curated out of which footage, which is real dataset provenance. It holds only
*human decisions*. Everything a machine produced (the frame cache, the detector's
boxes) lives in ``workspace/`` and is regenerable, so it is gitignored.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

VERSION = 1


def empty() -> dict:
    return {"version": VERSION, "clips": {}}


def load(path) -> dict:
    path = pathlib.Path(path)
    if not path.exists():
        return empty()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}\n"
                         "Fix it by hand, or delete it to start a fresh notebook.")
    data.setdefault("version", VERSION)
    data.setdefault("clips", {})
    return data


def save(path, data) -> None:
    """Atomic -- a crash mid-write must not truncate the notebook."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".nb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def entry(data: dict, clip: str) -> dict:
    return data["clips"].setdefault(clip, {"selected": [], "flipped": []})


def picked_as(n_boxes: int, flipped: bool) -> str:
    """What the human is asserting about this frame.

    The detector proposes; a flip overrules it. Recording the flip rather than
    the answer keeps both opinions, which is what later tells you how often the
    detector was wrong about a frame being empty.
    """
    has_sign = (n_boxes > 0) != flipped
    return "sign" if has_sign else "empty"
