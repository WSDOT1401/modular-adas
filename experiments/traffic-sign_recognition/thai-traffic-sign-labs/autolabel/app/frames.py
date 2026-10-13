"""Turn a video into stills, then ask the detector what is in them.

Two separate passes on purpose. Extract is cheap and you do it once; score is
~0.4 s a frame and you will want to redo it every time the detector is
retrained, without re-cutting frames you already have.
"""
from __future__ import annotations

import json
import pathlib

import cv2

THUMB_W = 768      # a 70px sign in a 2304px frame is 23px here -- small but visible
JPEG_Q = 95


def probe(video: pathlib.Path) -> dict:
    cap = cv2.VideoCapture(str(video))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()
    return {"fps": fps, "frames": n, "seconds": (n / fps) if fps else 0.0}


def _write_pair(img, full: pathlib.Path, thumb: pathlib.Path) -> None:
    cv2.imwrite(str(full), img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
    h, w = img.shape[:2]
    s = THUMB_W / w
    small = cv2.resize(img, (THUMB_W, max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(thumb), small, [cv2.IMWRITE_JPEG_QUALITY, 85])


def extract(video: pathlib.Path, out: pathlib.Path, interval_s: float,
            on_progress=None) -> dict:
    """Sample every ``interval_s`` by seeking, and record the frame we LANDED on.

    Not every dashcam writes well-formed MP4, so the number in the filename is
    always the frame actually decoded, never the one we asked for. A filename
    claiming ``_f000300`` is telling the truth.
    """
    (out / "full").mkdir(parents=True, exist_ok=True)
    (out / "thumb").mkdir(parents=True, exist_ok=True)
    for old in list((out / "full").glob("*.jpg")) + list((out / "thumb").glob("*.jpg")):
        old.unlink()

    meta = probe(video)
    stem = video.stem
    cap = cv2.VideoCapture(str(video))
    kept, want_t, i = [], 0.0, 0
    try:
        total = max(1, int(meta["seconds"] / interval_s) if meta["seconds"] else 1)
        while True:
            if meta["fps"]:
                cap.set(cv2.CAP_PROP_POS_MSEC, want_t * 1000.0)
            ok, img = cap.read()
            if not ok:
                break
            n = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            fid = f"{stem}_f{max(n, 0):06d}"
            h, w = img.shape[:2]
            _write_pair(img, out / "full" / f"{fid}.jpg", out / "thumb" / f"{fid}.jpg")
            kept.append({"id": fid, "n": max(n, 0), "t": round(want_t, 2),
                         "w": w, "h": h})
            i += 1
            if on_progress:
                on_progress(i, total)
            want_t += interval_s
            if meta["seconds"] and want_t > meta["seconds"]:
                break
            if not meta["fps"]:
                break
    finally:
        cap.release()

    payload = {"video": video.name, "interval_s": interval_s, "frames": kept}
    (out / "frames.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def load_index(out: pathlib.Path) -> dict | None:
    p = out / "frames.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def load_scores(out: pathlib.Path) -> dict:
    p = out / "scores.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()).get("frames", {})
    except json.JSONDecodeError:
        return {}


_MODELS: dict[str, object] = {}


def _model(path):
    """Load the detector once per process. Re-loading it for every clip costs
    seconds of dead time each and, worse, a second copy of the weights in RAM."""
    key = str(path)
    if key not in _MODELS:
        from ultralytics import YOLO
        _MODELS[key] = YOLO(key)
    return _MODELS[key]


def score(out: pathlib.Path, model_path, imgsz=1280, conf=0.25, on_progress=None) -> dict:
    """Run the detector over a clip's frames -> ``scores.json``.

    The boxes written here are the same ones ``prelabel.py detect`` will use, so
    the model runs once per frame for the whole pipeline, not once for the
    contact-sheet badge and again for pre-annotation.
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
    import classes

    idx = load_index(out)
    if not idx:
        raise RuntimeError("extract this clip first")
    paths = [str(out / "full" / f"{f['id']}.jpg") for f in idx["frames"]]
    model = _model(model_path)
    found = {}
    for i, (f, res) in enumerate(zip(idx["frames"],
                                     model.predict(source=paths, imgsz=imgsz, conf=conf,
                                                   stream=True, verbose=False)), 1):
        found[f["id"]] = [
            {"xyxy": [round(float(v), 1) for v in b.xyxy[0]],
             "coarse": classes.THAI3_NAMES[int(b.cls)],
             "conf": round(float(b.conf), 3)}
            for b in res.boxes]
        if on_progress:
            on_progress(i, len(paths))
    (out / "scores.json").write_text(json.dumps(
        {"model": str(model_path), "imgsz": imgsz, "conf": conf, "frames": found},
        indent=2) + "\n")
    return found
