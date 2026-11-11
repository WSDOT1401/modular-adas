"""Bundle the selected frames into a zip the labelling tool can swallow whole.

Images sit flat at the zip root because Roboflow, CVAT and Label Studio all
flatten nested uploads anyway -- and a flat archive keeps the source frame number
in the filename, which is the only thread tying a labelled image back to the
exact moment of footage it came from.

``manifest.csv`` rides along with the same provenance in machine-readable form,
so a later script can rebuild the selection without re-deriving it from filenames.

Archives are ZIP_STORED, not deflated: JPEG is already compressed, so deflating a
few hundred megabytes of it burns CPU to save roughly nothing.
"""

from __future__ import annotations

import csv
import io
import pathlib
import zipfile

MANIFEST_NAME = "manifest.csv"
MANIFEST_COLUMNS = ["filename", "source_video", "frame_number", "timestamp_s",
                    "width", "height", "interval_s"]


def zip_name(video_name: str, count: int) -> str:
    return f"{pathlib.Path(video_name).stem}_{count}frames.zip"


def bundle_name(frames: int, clips: int) -> str:
    """Name for a multi-clip export -- both numbers, because a zip of 1200 frames
    drawn from 3 clips is a different thing from one drawn from 30."""
    return f"dataset_{frames}frames_{clips}clips.zip"


def _manifest():
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    writer.writeheader()
    return buffer, writer


def _add(archive, writer, index: dict, selected_frames, full_dir) -> int:
    """Append one video's chosen frames to an open archive; return how many landed.

    Frames listed in ``selected_frames`` that are missing from the cache are
    skipped rather than raising, so one deleted jpg cannot cost you the whole
    export. The returned count is what is really in the zip -- callers record
    that, never the length of the request.
    """
    wanted = set(selected_frames)
    full_dir = pathlib.Path(full_dir)
    meta = index.get("meta", {})

    written = 0
    for row in index["frames"]:
        if row["frame"] not in wanted:
            continue
        source = full_dir / row["file"]
        if not source.exists():
            continue
        archive.write(source, arcname=row["file"])
        writer.writerow({
            "filename": row["file"],
            "source_video": index.get("video", ""),
            "frame_number": row["frame"],
            "timestamp_s": row["t"],
            "width": meta.get("width", ""),
            "height": meta.get("height", ""),
            "interval_s": index.get("interval_s", ""),
        })
        written += 1
    return written


def build(index: dict, selected_frames, full_dir, dest_path) -> int:
    """Write a zip of one video's chosen frames to ``dest_path``; return the count."""
    buffer, writer = _manifest()
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_STORED) as archive:
        written = _add(archive, writer, index, selected_frames, full_dir)
        archive.writestr(MANIFEST_NAME, buffer.getvalue())
    return written


def build_many(items, dest_path) -> dict:
    """Write one zip spanning several videos; return ``{video_name: frames written}``.

    ``items`` is ``(video_name, index, selected_frames, full_dir)`` per video.
    Frame files already carry the video's stem (``clip_f000123.jpg``), so a flat
    merged archive cannot collide, and one manifest covers the lot -- its
    ``source_video`` column is what says where each frame came from.
    """
    buffer, writer = _manifest()
    counts = {}
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_STORED) as archive:
        for name, index, selected_frames, full_dir in items:
            landed = _add(archive, writer, index, selected_frames, full_dir)
            if landed:
                counts[name] = landed
        archive.writestr(MANIFEST_NAME, buffer.getvalue())
    return counts
