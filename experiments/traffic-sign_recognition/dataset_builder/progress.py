"""On-disk record of which frames were curated out of which footage.

``progress.json`` is tracked in git on purpose: it is the lab notebook for the
dataset. It stores only *facts* -- when a clip was extracted, which source frame
numbers were kept, when a zip was built. The three-state icon on the homepage is
derived from those facts on every page load and never written down, so it cannot
drift out of sync with what actually happened.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone

SCHEMA_VERSION = 1
DEFAULT_TARGET = 500

UNTOUCHED = "untouched"      # never extracted
IN_PROGRESS = "in_progress"  # extracted, maybe selected, never downloaded
DONE = "done"                # downloaded at least once


def now_iso() -> str:
    """Local time with an explicit offset -- a bare timestamp is unreadable later."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def empty() -> dict:
    return {"version": SCHEMA_VERSION, "target_frames": DEFAULT_TARGET, "videos": {}}


def load(path) -> dict:
    path = pathlib.Path(path)
    if not path.exists():
        return empty()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path} is not valid JSON: {exc}\n"
            "Fix it by hand, or delete it to start a fresh notebook."
        ) from exc
    data.setdefault("version", SCHEMA_VERSION)
    data.setdefault("target_frames", DEFAULT_TARGET)
    data.setdefault("videos", {})
    return data


def save(path, data) -> None:
    """Write atomically -- a crash mid-write must not truncate the notebook."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".progress-", suffix=".tmp")
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


def entry(data: dict, name: str) -> dict:
    """The record for one video, created empty on first touch."""
    return data["videos"].setdefault(name, {"selected": [], "downloads": []})


def state_of(record: dict | None) -> str:
    if not record or not record.get("extract"):
        return UNTOUCHED
    return DONE if record.get("downloads") else IN_PROGRESS


def total_selected(data: dict) -> int:
    return sum(len(v.get("selected", [])) for v in data["videos"].values())


def total_downloaded(data: dict) -> int:
    """Frames in the most recent download of each video -- what actually left the app."""
    total = 0
    for record in data["videos"].values():
        downloads = record.get("downloads") or []
        if downloads:
            total += downloads[-1].get("count", 0)
    return total
