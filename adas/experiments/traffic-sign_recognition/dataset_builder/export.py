"""Bundle the selected frames into a zip the labelling tool can swallow whole.

Images sit flat at the zip root because Roboflow, CVAT and Label Studio all
flatten nested uploads anyway -- and a flat archive keeps the source frame number
in the filename, which is the only thread tying a labelled image back to the
exact moment of footage it came from.

``manifest.csv`` rides along with the same provenance in machine-readable form,
so a later script can rebuild the selection without re-deriving it from filenames.
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


def build(index: dict, selected_frames, full_dir, dest_path) -> int:
    """Write a zip of the chosen frames to ``dest_path``; return how many landed.

    Frames listed in ``selected_frames`` that are missing from the cache are
    skipped rather than raising, so one deleted jpg cannot cost you the whole
    export. The returned count is what is really in the zip -- callers record
    that, never the length of the request.
    """
    wanted = set(selected_frames)
    full_dir = pathlib.Path(full_dir)
    meta = index.get("meta", {})
    rows = [f for f in index["frames"] if f["frame"] in wanted]

    manifest = io.StringIO()
    writer = csv.DictWriter(manifest, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    writer.writeheader()

    written = 0
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_STORED) as archive:
        # ZIP_STORED, not DEFLATE: JPEG is already compressed, so deflating it
        # burns CPU on a few hundred megabytes to save roughly nothing.
        for row in rows:
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
        archive.writestr(MANIFEST_NAME, manifest.getvalue())
    return written
