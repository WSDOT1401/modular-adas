#!/usr/bin/env python3
"""Step 1 of the pipeline: footage in, a batch of picked frames out.

    python app.py            # http://127.0.0.1:5001

Drop videos in ``footage/``, Extract them into stills, Score them with the sign
detector, then pick the frames worth labelling off a contact sheet. The badge in
each thumbnail's corner is how many signs the detector found; click it when the
detector is wrong. The counter at the top shows how close you are to the share of
sign-free frames you want.

Press Create batch and the picks become ``batches/<id>-<date>/``, which
``prelabel.py`` takes from there.

Binds to 127.0.0.1 only. It reads and writes files on your machine with no
authentication -- do not expose it to a network. Port 5001, not 5000, because
macOS AirPlay Receiver listens on [::1]:5000 and a browser that resolves
localhost to IPv6 reaches AirPlay instead.
"""
from __future__ import annotations

import argparse
import pathlib
import queue
import sys
import threading
import traceback
import uuid

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, url_for)

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import frames as F          # noqa: E402
import prelabel             # noqa: E402
import store                # noqa: E402

FOOTAGE = HERE / "footage"
WORKSPACE = HERE / "workspace" / "frames"
NOTEBOOK = HERE / "notebook.json"
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".m2ts", ".ts", ".webm"}

app = Flask(__name__)
# One lock for the notebook: two overlapping autosaves would otherwise clobber
# each other's picks. ponytail: a single global lock, because there is exactly
# one human clicking.
LOCK = threading.Lock()
JOBS: dict[str, dict] = {}

# Jobs run ONE AT A TIME, through a single worker. Ticking 60 clips used to
# spawn 60 threads, each decoding 2304x1296 video or holding its own copy of
# the detector; on a laptop that does not fail cleanly, it just grinds -- two
# concurrent score jobs measured 3.7 s/frame against 0.55 s/frame alone.
# ponytail: one worker, because the bottleneck is this machine, not the queue.
QUEUE: "queue.Queue[tuple[str, object]]" = queue.Queue()


# -------------------------------------------------------------------- data --

def clip_names() -> list[str]:
    if not FOOTAGE.exists():
        return []
    return sorted(p.stem for p in FOOTAGE.iterdir()
                  if p.suffix.lower() in VIDEO_EXT and not p.name.startswith("."))


def video_for(clip: str) -> pathlib.Path:
    for p in FOOTAGE.iterdir():
        if p.stem == clip and p.suffix.lower() in VIDEO_EXT:
            return p
    abort(404, f"no video named {clip}")


def safe(clip: str) -> str:
    """A clip name reaches us from the URL, so it must not escape the workspace."""
    if clip != pathlib.PurePath(clip).name or clip in ("", ".", ".."):
        abort(400, "bad clip name")
    return clip


def summarise(clip: str, nb: dict) -> dict:
    out = WORKSPACE / clip
    idx = F.load_index(out)
    scores = F.load_scores(out)
    rec = nb["clips"].get(clip, {})
    sel = set(rec.get("selected") or [])
    flip = set(rec.get("flipped") or [])
    n_sign = sum(1 for f in sel
                 if store.picked_as(len(scores.get(f, [])), f in flip) == "sign")
    return {
        "name": clip,
        "extracted": len(idx["frames"]) if idx else 0,
        "scored": len(scores),
        "selected": len(sel),
        "sign": n_sign,
        "empty": len(sel) - n_sign,
        "state": ("picked" if sel else "scored" if scores else "extracted" if idx else "new"),
    }


# -------------------------------------------------------------------- jobs --

def _worker() -> None:
    while True:
        jid, fn = QUEUE.get()
        job = JOBS[jid]
        job["state"] = "running"
        try:
            fn(lambda i, n: job.update(done=i, total=n))
            job["state"] = "done"
        except Exception as exc:                      # noqa: BLE001
            traceback.print_exc()
            job.update(state="error", error=f"{type(exc).__name__}: {exc}")
        QUEUE.task_done()


threading.Thread(target=_worker, daemon=True).start()


def start(fn, label: str) -> str:
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"label": label, "done": 0, "total": 0, "error": None,
                 "state": "queued", "ahead": QUEUE.qsize()}
    QUEUE.put((jid, fn))
    return jid


def busy_with(clip: str) -> str | None:
    """Is a job for this clip queued or running? The contact sheet needs to say
    so, because a frame nobody has scored yet and a frame with no sign on it
    look identical -- both show an empty badge."""
    for j in JOBS.values():
        if j["state"] in ("queued", "running") and j["label"].endswith(" " + clip):
            return j["label"].split()[0]
    return None


@app.get("/job/<jid>")
def job(jid: str):
    return jsonify(JOBS.get(jid) or {"state": "unknown"})


# ------------------------------------------------------------------ routes --

@app.get("/")
def index():
    nb = store.load(NOTEBOOK)
    clips = [summarise(c, nb) for c in clip_names()]
    picked = sum(c["selected"] for c in clips)
    empty = sum(c["empty"] for c in clips)
    return render_template("index.html", clips=clips, picked=picked, empty=empty,
                           footage=FOOTAGE,
                           pct=round(100 * empty / picked) if picked else 0)


@app.post("/clip/<clip>/extract")
def do_extract(clip: str):
    clip = safe(clip)
    video = video_for(clip)
    interval = max(0.1, float(request.form.get("interval", 2.0)))
    out = WORKSPACE / clip
    jid = start(lambda cb: F.extract(video, out, interval, cb), f"extract {clip}")
    return jsonify(job=jid)


@app.post("/clip/<clip>/score")
def do_score(clip: str):
    clip = safe(clip)
    out = WORKSPACE / clip
    if not F.load_index(out):
        abort(409, "extract this clip first")
    jid = start(lambda cb: F.score(out, prelabel.MODEL, on_progress=cb), f"score {clip}")
    return jsonify(job=jid)


@app.get("/clip/<clip>")
def sheet(clip: str):
    clip = safe(clip)
    out = WORKSPACE / clip
    idx = F.load_index(out)
    if not idx:
        return redirect(url_for("index"))
    scores = F.load_scores(out)
    nb = store.load(NOTEBOOK)
    rec = nb["clips"].get(clip, {})
    sel, flip = set(rec.get("selected") or []), set(rec.get("flipped") or [])
    items = [{
        "id": f["id"], "t": f["t"], "n": f["n"],
        "boxes": len(scores.get(f["id"], [])),
        "picked": f["id"] in sel,
        "flipped": f["id"] in flip,
    } for f in idx["frames"]]
    return render_template("sheet.html", clip=clip, items=items,
                           scored=bool(scores), interval=idx["interval_s"],
                           busy=busy_with(clip))


@app.post("/clip/<clip>/selection")
def save_selection(clip: str):
    clip = safe(clip)
    payload = request.get_json(silent=True) or {}
    with LOCK:
        nb = store.load(NOTEBOOK)
        rec = store.entry(nb, clip)
        rec["selected"] = sorted(set(payload.get("selected") or []))
        rec["flipped"] = sorted(set(payload.get("flipped") or []))
        store.save(NOTEBOOK, nb)
    return jsonify(saved=len(rec["selected"]))


@app.post("/batch")
def make_batch():
    bid = (request.form.get("bid") or "").strip()
    want = request.form.getlist("clip")
    if not bid or not bid.isalnum():
        abort(400, "batch id must be alphanumeric, e.g. b01")
    if not want:
        abort(400, "tick at least one clip")

    nb = store.load(NOTEBOOK)
    picks = []
    for clip in want:
        scores = F.load_scores(WORKSPACE / clip)
        rec = nb["clips"].get(clip, {})
        flip = set(rec.get("flipped") or [])
        for fid in rec.get("selected") or []:
            picks.append((clip, fid,
                          store.picked_as(len(scores.get(fid, [])), fid in flip)))
    if not picks:
        abort(409, "none of those clips have picked frames")

    try:
        prelabel.create(bid, picks, WORKSPACE)
    except SystemExit as exc:
        abort(409, str(exc))
    return redirect(url_for("index"))


@app.get("/img/<kind>/<clip>/<fid>.jpg")
def img(kind: str, clip: str, fid: str):
    if kind not in ("full", "thumb"):
        abort(404)
    clip, fid = safe(clip), safe(fid)
    p = WORKSPACE / clip / kind / f"{fid}.jpg"
    if not p.exists():
        abort(404)
    return send_file(p, mimetype="image/jpeg")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    FOOTAGE.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    print(f"footage: {FOOTAGE}\nopen http://127.0.0.1:{a.port}")
    app.run(host="127.0.0.1", port=a.port, debug=a.debug)


if __name__ == "__main__":
    main()
