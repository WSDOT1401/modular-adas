"""Discover the footage on disk and join it against the progress notebook.

The video name arrives from the URL, so it is untrusted input. Every lookup goes
through :func:`resolve`, which matches the name against the *discovered* catalog
instead of joining it onto a path -- a name like ``../../.ssh/id_rsa`` simply
fails to match anything and 404s.
"""

from __future__ import annotations

import pathlib
import shutil

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
            # Archiving is a flag, not a move: the file stays put and the flag
            # only decides which tab the row lands on.
            "archived": bool(record.get("archived")),
            "download_count": len(downloads),
            # A cache wiped by hand must not leave the homepage claiming frames exist.
            "unreadable": bool((record.get("meta") or {}).get("error")),
            "stale": bool(record.get("extract")) and index is None,
        })
    return rows


def trash(path) -> pathlib.Path:
    """Move a file to the Trash rather than unlinking it.

    Deleting a clip is one click on original footage that may not exist anywhere
    else, so it goes somewhere Finder can put it back. With no ``~/.Trash`` it
    lands in ``footage/.trash`` instead -- still recoverable, and still invisible
    to :func:`list_videos`, which only ever counts files.
    """
    path = pathlib.Path(path)
    bin_dir = pathlib.Path.home() / ".Trash"
    if not bin_dir.is_dir():
        bin_dir = path.parent / ".trash"
        bin_dir.mkdir(exist_ok=True)
    dest, n = bin_dir / path.name, 2
    while dest.exists():                      # Finder's own "name 2.ext" shape
        dest, n = bin_dir / f"{path.stem} {n}{path.suffix}", n + 1
    # move, not rename: ~/.Trash is usually on a different volume from footage.
    shutil.move(str(path), str(dest))
    return dest
