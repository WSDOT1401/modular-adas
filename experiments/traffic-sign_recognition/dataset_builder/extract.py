"""Sample still frames out of dashcam footage at a fixed time interval.

Consecutive video frames are near-identical, so a dataset built from *every*
frame is mostly duplicates that teach a detector nothing. Sampling every 1-3
seconds is what turns footage into training data.

Frames are located by seeking rather than by decoding the whole file, so the
cost scales with the number of frames you *want* rather than with the length of
the clip -- on a 20-minute video that is the difference between seconds and a
minute. Seeking is frame-accurate on well-formed MP4, but not every dashcam
writes well-formed MP4, so we record the frame we actually *landed* on rather
than the one we asked for. A filename that claims ``_f000060`` is then always
telling the truth.
"""

from __future__ import annotations

import json
import pathlib

import cv2

THUMB_WIDTH = 320
FULL_QUALITY = 95   # source is already H.264-lossy; q95 adds nothing visible
THUMB_QUALITY = 80
MIN_INTERVAL_S = 0.1
MAX_INTERVAL_S = 60.0

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".m2ts", ".ts", ".webm"}


class ExtractError(RuntimeError):
    """The video could not be read at all -- codec, permissions, or corruption."""


def probe(video_path) -> dict:
    """Container metadata, with the lies dashcams tell normalised away."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ExtractError(f"OpenCV cannot open {pathlib.Path(video_path).name}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()

    # Some cameras report 0 or an absurd fps. Anything outside this range is junk.
    trusted_fps = fps if 1.0 <= fps <= 240.0 else 0.0
    duration = count / trusted_fps if trusted_fps and count > 0 else 0.0
    return {
        "fps": round(trusted_fps, 3),
        "frame_count": count if count > 0 else 0,
        "width": width,
        "height": height,
        "duration_s": round(duration, 2),
        "seekable": bool(trusted_fps and count > 0),
    }


def _write_pair(frame, full_path: pathlib.Path, thumb_path: pathlib.Path) -> None:
    cv2.imwrite(str(full_path), frame, [cv2.IMWRITE_JPEG_QUALITY, FULL_QUALITY])
    height, width = frame.shape[:2]
    thumb_h = max(1, round(THUMB_WIDTH * height / width))
    thumb = cv2.resize(frame, (THUMB_WIDTH, thumb_h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(thumb_path), thumb, [cv2.IMWRITE_JPEG_QUALITY, THUMB_QUALITY])


def extract(video_path, out_dir, interval_s: float, on_progress=None) -> list[dict]:
    """Write sampled frames under ``out_dir`` and return the frame index.

    ``on_progress(done, total)`` is called as work proceeds so a long clip can
    show something other than a frozen browser tab.
    """
    if not (MIN_INTERVAL_S <= interval_s <= MAX_INTERVAL_S):
        raise ValueError(f"interval must be {MIN_INTERVAL_S}-{MAX_INTERVAL_S}s, got {interval_s}")

    video_path = pathlib.Path(video_path)
    out_dir = pathlib.Path(out_dir)
    full_dir, thumb_dir = out_dir / "full", out_dir / "thumb"
    for directory in (full_dir, thumb_dir):
        directory.mkdir(parents=True, exist_ok=True)
        for stale in directory.glob("*.jpg"):
            stale.unlink()   # a re-extract replaces the set; leftovers would be ghosts

    meta = probe(video_path)
    stem = video_path.stem
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ExtractError(f"OpenCV cannot open {video_path.name}")

    frames: list[dict] = []
    seen: set[int] = set()

    def record(frame, number: int, seconds: float) -> None:
        if number in seen:
            return          # a coarse seek can land twice on the same frame
        seen.add(number)
        name = f"{stem}_f{number:06d}.jpg"
        _write_pair(frame, full_dir / name, thumb_dir / name)
        frames.append({"frame": number, "t": round(seconds, 3), "file": name})

    try:
        if meta["seekable"]:
            step = max(1, round(meta["fps"] * interval_s))
            wanted = list(range(0, meta["frame_count"], step))
            for done, target in enumerate(wanted, start=1):
                cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                ok, frame = cap.read()
                if not ok:
                    continue    # past the real end; containers over-report frame counts
                landed = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                if landed < 0:
                    landed = target
                record(frame, landed, landed / meta["fps"])
                if on_progress:
                    on_progress(done, len(wanted))
        else:
            # No trustworthy fps or frame count: walk the file and use wall-clock
            # timestamps. Slower, but it works on anything OpenCV can decode.
            next_t, index = 0.0, 0
            while True:
                if not cap.grab():
                    break
                seconds = (cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
                if seconds + 1e-6 >= next_t:
                    ok, frame = cap.retrieve()
                    if ok:
                        record(frame, index, seconds)
                        next_t = seconds + interval_s
                        if on_progress:
                            on_progress(len(frames), 0)
                index += 1
    finally:
        cap.release()

    if not frames:
        raise ExtractError(
            f"{video_path.name} decoded 0 frames. The file may be truncated or "
            "use a codec this OpenCV build cannot read."
        )

    index_payload = {"video": video_path.name, "interval_s": interval_s,
                     "meta": meta, "frames": frames}
    (out_dir / "frames.json").write_text(json.dumps(index_payload, indent=2) + "\n")
    return frames


def load_index(out_dir) -> dict | None:
    path = pathlib.Path(out_dir) / "frames.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
