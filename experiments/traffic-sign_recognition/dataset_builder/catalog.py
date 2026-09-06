"""Discover the footage on disk and join it against the progress notebook.

The video name arrives from the URL, so it is untrusted input. Every lookup goes
through :func:`resolve`, which matches the name against the *discovered* catalog
instead of joining it onto a path -- a name like ``../../.ssh/id_rsa`` simply
fails to match anything and 404s.
"""

from __future__ import annotations

import pathlib

from extract import VIDEO_SUFFIXES
import progress


def list_videos(footage_dir) -> list[dict]:
    """Every readable video in ``footage_dir``, newest name first, deterministic."""
    footage_dir = pathlib.Path(footage_dir)
    if not footage_dir.is_dir():
        return []
    found = []
    for path in sorted(footage_dir.iterdir(), key=lambda p: p.name):
        if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
            continue
        stat = path.stat()
        found.append({"name": path.name, "path": path,
                      "size_bytes": stat.st_size, "mtime": stat.st_mtime})
    return found


def resolve(footage_dir, name: str) -> pathlib.Path | None:
    """The path for ``name``, or None if it is not a video we actually found."""
    for video in list_videos(footage_dir):
        if video["name"] == name:
            return video["path"]
    return None


def workspace_for(workspace_dir, name: str) -> pathlib.Path:
    """Frame cache directory for one video.

    Keyed by stem, so ``clip.mp4`` and ``clip.MOV`` would collide -- callers must
    resolve against the catalog first, which makes a collision visible as two
    real files rather than a silent overwrite.
    """
    return pathlib.Path(workspace_dir) / "frames" / pathlib.Path(name).stem


def describe(footage_dir, workspace_dir, data: dict) -> list[dict]:
    """One row per video for the homepage: file facts + progress + derived state."""
    from extract import load_index

    rows = []
    for video in list_videos(footage_dir):
        record = data["videos"].get(video["name"], {})
        index = load_index(workspace_for(workspace_dir, video["name"]))
        downloads = record.get("downloads") or []
        rows.append({
            "name": video["name"],
            "size_mb": round(video["size_bytes"] / 1e6, 1),
            "state": progress.state_of(record),
            "extracted": len(index["frames"]) if index else 0,
            "interval_s": (record.get("extract") or {}).get("interval_s"),
            "duration_s": (record.get("meta") or {}).get("duration_s")
                          or (index or {}).get("meta", {}).get("duration_s") or 0,
            "selected": len(record.get("selected") or []),
            "last_download": downloads[-1]["at"] if downloads else None,
            "download_count": len(downloads),
            # A cache wiped by hand must not leave the homepage claiming frames exist.
            "unreadable": bool((record.get("meta") or {}).get("error")),
            "stale": bool(record.get("extract")) and index is None,
        })
    return rows
