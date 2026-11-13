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


def best_device(device=None):
    """ultralytics picks CPU on macOS even when MPS is right there, which costs
    about 10x -- the difference between an overnight batch and a coffee break."""
    if device is not None:
        return device
    import torch
    return "mps" if torch.backends.mps.is_available() else None


def _model(path):
    """Load the detector once per process. Re-loading it for every clip costs
    seconds of dead time each and, worse, a second copy of the weights in RAM."""
    key = str(path)
    if key not in _MODELS:
        from ultralytics import YOLO
        _MODELS[key] = YOLO(key)
    return _MODELS[key]


def score(out: pathlib.Path, model_path, imgsz=1280, conf=0.25, on_progress=None,
          device=None) -> dict:
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

    # Keep what this same model already decided and score only the gaps. A clip
    # that gained ten frames should cost ten frames of work, not two hundred.
    # A DIFFERENT model means every verdict is stale, so start clean.
    prev, old_model = {}, None
    sp = out / "scores.json"
    if sp.exists():
        try:
            blob = json.loads(sp.read_text())
            old_model, prev = blob.get("model"), blob.get("frames", {})
        except json.JSONDecodeError:
            pass
    found = dict(prev) if old_model == str(model_path) else {}

    todo = [f for f in idx["frames"] if f["id"] not in found]
    if not todo:
        if on_progress:
            on_progress(len(idx["frames"]), len(idx["frames"]))
        return found

    paths = [str(out / "full" / f"{f['id']}.jpg") for f in todo]
    model = _model(model_path)
    for i, (f, res) in enumerate(zip(todo,
                                     model.predict(source=paths, imgsz=imgsz, conf=conf,
                                                   stream=True, device=best_device(device),
                                                   verbose=False)), 1):
        found[f["id"]] = [
            {"xyxy": [round(float(v), 1) for v in b.xyxy[0]],
             "coarse": classes.THAI3_NAMES[int(b.cls)],
             "conf": round(float(b.conf), 3)}
            for b in res.boxes]
        if on_progress:
            on_progress(i, len(todo))
    (out / "scores.json").write_text(json.dumps(
        {"model": str(model_path), "imgsz": imgsz, "conf": conf, "frames": found},
        indent=2) + "\n")
    return found


# --------------------------------------------------------------- picking --

# Both numbers are in NETWORK-input pixels, not source pixels, so they mean the
# same thing on a 2304-wide clip and a 720p one -- the per-clip scale factor does
# the converting. 16 px is M1's trained size floor (the floor16 run); under it
# `build` deletes the box at training time anyway, so surfacing it only spends a
# reviewer's attention on data we throw away.
FLOOR = 16
GROWTH = 1.5     # a sign earns another frame once it is half again as big
EDGE = 2         # px of slack before a box counts as cut by the frame border


def touches_edge(x1, y1, x2, y2, w, h) -> bool:
    """Has the frame border cut this box in half?

    Driving past a sign makes it bigger AND pushes it out of frame, so the growth
    rule below reaches for the biggest view -- which is the last instant before
    the sign leaves, half of it already gone. M1 does not mind; a clipped sign is
    a normal thing for a detector to see. M2 does: half a no-left-turn is not a
    small no-left-turn, it is a red arc, and training on it teaches the wrong
    shape. So a cut box neither earns a frame nor counts as having been captured.
    """
    return x1 <= EDGE or y1 <= EDGE or x2 >= w - EDGE or y2 >= h - EDGE


def worth_a_frame(last_px: float | None, px: float) -> bool:
    """Is this sign different enough from the last time we kept a frame of it?

    Fixed size bands were the obvious first try and they jitter: a sign sitting
    near an edge flips bands on a one-pixel change and buys a second, identical
    frame. A ratio has no edges to sit on.
    """
    if px < FLOOR:
        return False
    return last_px is None or px >= last_px * GROWTH


def pick(video: pathlib.Path, out: pathlib.Path, model_path, imgsz=1280, conf=0.15,
         on_progress=None, device=None) -> dict:
    """Track every sign through the clip; keep one frame per sign per size band.

    The replacement for ``extract``'s every-N-seconds sampling. Time is the wrong
    ruler: you drive past one sign over about three seconds, so a one-second
    interval still hands the reviewer three near-identical pictures of it. What
    makes two frames worth looking at separately is the sign being a different
    SIZE -- scale is the hardest axis for a detector, and the only one that
    sampling by clock is blind to.

    Runs well below the confidence you would ship, on purpose. A detector only
    ever surfaces signs it already finds, so at conf=0.5 it can never show you
    the ones it misses, and the labels it produces quietly teach it to keep
    missing them. The bands are what make that affordable: a lamppost tracked
    across 200 frames still only ever costs three frames.
    """
    (out / "full").mkdir(parents=True, exist_ok=True)
    (out / "thumb").mkdir(parents=True, exist_ok=True)
    for old in list((out / "full").glob("*.jpg")) + list((out / "thumb").glob("*.jpg")):
        old.unlink()

    device = best_device(device)
    meta = probe(video)
    stem, model = video.stem, _model(model_path)
    last: dict[int, float] = {}        # track id -> network px when last kept
    kept, found = [], {}
    total = max(1, meta["frames"])

    for n, res in enumerate(model.track(source=str(video), stream=True, imgsz=imgsz,
                                        conf=conf, persist=True, device=device,
                                        verbose=False)):
        img = res.orig_img
        h, w = img.shape[:2]
        scale = imgsz / max(w, h)          # source px -> network px, per clip
        here = []
        for b in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            px = min(x2 - x1, y2 - y1) * scale
            if px < FLOOR or touches_edge(x1, y1, x2, y2, w, h):
                continue
            # Every untracked box shares id -1 rather than becoming its own
            # track, so a burst of unidentified junk cannot flood the batch.
            here.append((int(b.id) if b.id is not None else -1, px))
        if on_progress:
            on_progress(n + 1, total)
        if not any(worth_a_frame(last.get(t), px) for t, px in here):
            continue
        # Credit every sign visible here, not just the one that fired: this frame
        # is a picture of all of them, so none of them needs its own frame yet.
        last.update(here)

        fid = f"{stem}_f{n:06d}"
        _write_pair(img, out / "full" / f"{fid}.jpg", out / "thumb" / f"{fid}.jpg")
        kept.append({"id": fid, "n": n, "w": w, "h": h,
                     "t": round(n / meta["fps"], 2) if meta["fps"] else 0.0})
        # Every box on the frame, including the ones below the floor. A sign left
        # unboxed teaches the detector that a sign is background, so the reviewer
        # has to see all of them -- the floor decides what trains, not what shows.
        # The track id is the only thing that says "these two boxes are the same
        # physical sign". Worth storing: it is what lets a count of unique SIGNS
        # replace a count of unique clips when measuring how much data we have.
        found[fid] = [{"xyxy": [round(float(v), 1) for v in b.xyxy[0]],
                       "coarse": res.names[int(b.cls)],
                       "tid": int(b.id) if b.id is not None else None,
                       "conf": round(float(b.conf), 3)} for b in res.boxes]

    payload = {"video": video.name, "interval_s": 0, "picked_by": "track",
               "floor": FLOOR, "growth": GROWTH, "frames": kept}
    (out / "frames.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out / "scores.json").write_text(json.dumps(
        {"model": str(model_path), "imgsz": imgsz, "conf": conf, "frames": found},
        indent=2) + "\n")
    return payload


if __name__ == "__main__":
    assert not worth_a_frame(None, 15.9), "below the floor is never worth a frame"
    assert worth_a_frame(None, 16), "first sighting above the floor always counts"
    assert not worth_a_frame(20, 29.9) and worth_a_frame(20, 30), "needs 1.5x"
    assert not worth_a_frame(20, 10), "a sign getting smaller is not news"

    assert touches_edge(0, 50, 80, 120, 1920, 1080), "cut by the left border"
    assert touches_edge(1850, 50, 1919, 120, 1920, 1080), "cut by the right border"
    assert touches_edge(100, 0, 180, 120, 1920, 1080), "cut by the top"
    assert not touches_edge(100, 50, 180, 120, 1920, 1080), "well inside is fine"

    # The point of the whole thing: one sign getting closer, one frame per step.
    last, out = None, []
    for px in (20, 21, 22, 30, 31, 32, 50, 300):
        if worth_a_frame(last, px):
            last = px
            out.append(px)
    assert out == [20, 30, 50, 300], out

    # And the edge case that killed fixed bands: jitter around a threshold.
    last, n = 24.0, 0
    for px in (24.9, 25.1, 24.8, 25.2, 24.7):
        if worth_a_frame(last, px):
            last = px
            n += 1
    assert n == 0, "a jittering sign must not buy a second frame"
    print("ok")
