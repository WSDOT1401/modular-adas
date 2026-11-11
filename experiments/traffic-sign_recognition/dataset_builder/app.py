"""Local web app for turning dashcam footage into a curated frame set.

Run it, drop videos in ``footage/``, open the browser: pick a clip, extract
frames every N seconds, click the ones worth labelling, download a zip. The zip
goes to a labelling tool (Roboflow / CVAT / Label Studio); this app deliberately
does not draw boxes.

Binds to 127.0.0.1 only. It reads and writes files on your machine with no
authentication, so it must never be reachable from the network.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import threading
import traceback

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, url_for)

import catalog
import export
import extract
import progress

HERE = pathlib.Path(__file__).resolve().parent
FOOTAGE_DIR = HERE / "footage"
WORKSPACE_DIR = HERE / "workspace"
PROGRESS_PATH = HERE / "progress.json"
DEFAULT_INTERVAL_S = 2.0

app = Flask(__name__)
app.config.update(FOOTAGE_DIR=FOOTAGE_DIR, WORKSPACE_DIR=WORKSPACE_DIR,
                  PROGRESS_PATH=PROGRESS_PATH)

# Extraction runs off-thread so a 20-minute clip shows a progress bar instead of
# a frozen tab. One job per video; the dict is small and lives for the process.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
# Serialises read-modify-write on progress.json. Autosave fires on every click,
# and two overlapping requests would otherwise clobber each other's selections.
_notebook_lock = threading.Lock()


def _paths():
    return (app.config["FOOTAGE_DIR"], app.config["WORKSPACE_DIR"],
            app.config["PROGRESS_PATH"])


def _video_or_404(name: str) -> pathlib.Path:
    footage_dir, _, _ = _paths()
    path = catalog.resolve(footage_dir, name)
    if path is None:
        abort(404, f"No video named {name!r} in {footage_dir}")
    return path


def _job(name: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(name)
        return dict(job) if job else None


def _set_job(name: str, **fields) -> None:
    with _jobs_lock:
        _jobs.setdefault(name, {}).update(fields)


def _ensure_meta(data: dict, footage_dir) -> bool:
    """Probe any clip we have not measured yet, so the homepage can show its
    length before you commit to extracting it. Probing is cheap but not free, so
    the result is cached into the notebook and never re-read."""
    changed = False
    for video in catalog.list_videos(footage_dir):
        record = progress.entry(data, video["name"])
        if record.get("meta"):
            continue
        try:
            record["meta"] = extract.probe(video["path"])
        except extract.ExtractError as exc:
            # An unreadable file must still list, flagged -- not crash the homepage.
            record["meta"] = {"error": str(exc), "duration_s": 0, "fps": 0,
                              "frame_count": 0, "width": 0, "height": 0,
                              "seekable": False}
        changed = True
    return changed


@app.template_filter("clock")
def clock(seconds) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


@app.route("/")
def index():
    footage_dir, workspace_dir, progress_path = _paths()
    with _notebook_lock:
        data = progress.load(progress_path)
        if _ensure_meta(data, footage_dir):
            progress.save(progress_path, data)
    rows = catalog.describe(footage_dir, workspace_dir, data)
    archived_tab = request.args.get("tab") == "archived"
    target = max(1, int(data.get("target_frames") or progress.DEFAULT_TARGET))
    selected = progress.total_selected(data)
    return render_template(
        "index.html",
        # Only the table is filtered. The totals below stay whole-catalog: those
        # frames were really curated, so tidying up must not make the number drop.
        videos=[r for r in rows if r["archived"] == archived_tab],
        archived_tab=archived_tab,
        tabs={"archived": sum(1 for r in rows if r["archived"]),
              "active": sum(1 for r in rows if not r["archived"])},
        target=target, selected=selected,
        downloaded=progress.total_downloaded(data),
        pct=min(100, round(100 * selected / target)),
        footage_dir=footage_dir,
        counts={state: sum(1 for r in rows if r["state"] == state)
                for state in (progress.UNTOUCHED, progress.IN_PROGRESS, progress.DONE)},
    )


@app.post("/target")
def set_target():
    _, _, progress_path = _paths()
    try:
        target = int(request.form.get("target", ""))
    except ValueError:
        target = progress.DEFAULT_TARGET
    with _notebook_lock:
        data = progress.load(progress_path)
        data["target_frames"] = max(1, target)
        progress.save(progress_path, data)
    return redirect(url_for("index"))


@app.post("/archive")
def archive_videos():
    """Move the ticked clips between the Active and Archived tabs.

    Nothing happens on disk: archiving sets a flag, so the frame cache, the
    selections and the file itself are untouched and the button on the other tab
    puts them straight back. Which way it goes is the tab you pressed it from.
    """
    footage_dir, _, progress_path = _paths()
    tab = request.form.get("tab")
    archived = tab != "archived"
    with _notebook_lock:
        data = progress.load(progress_path)
        for name in request.form.getlist("name"):
            if catalog.resolve(footage_dir, name) is None:
                continue                      # gone from footage/; nothing to file
            record = progress.entry(data, name)
            if archived:
                record["archived"] = True
            else:
                record.pop("archived", None)  # popped, not False: the notebook is committed
        progress.save(progress_path, data)
    return redirect(url_for("index", tab=tab or None))


@app.post("/delete")
def delete_videos():
    """Move unwanted clips to the Trash, with their frame cache and notebook row.

    The video is trashed rather than unlinked: this is a one-click action on
    original footage, so it has to be undoable from Finder. The frame cache is
    not -- it is derived, and the README already calls it safe to delete.
    """
    footage_dir, workspace_dir, progress_path = _paths()
    with _notebook_lock:
        data = progress.load(progress_path)
        for name in request.form.getlist("name"):
            path = catalog.resolve(footage_dir, name)
            if path is None:
                continue                      # already gone; nothing left to undo
            catalog.trash(path)
            shutil.rmtree(catalog.workspace_for(workspace_dir, name), ignore_errors=True)
            data["videos"].pop(name, None)
        progress.save(progress_path, data)
    return redirect(url_for("index", tab=request.form.get("tab") or None))


@app.post("/zip")
def download_many():
    """One zip for every clip you ticked, instead of one download per clip.

    A clip you never curated contributes nothing and is skipped rather than
    refused -- ticking the whole list to grab everything selected so far is the
    point of the button. Each clip that does contribute gets its own download
    recorded, exactly as the per-clip button would.
    """
    footage_dir, workspace_dir, progress_path = _paths()
    data = progress.load(progress_path)
    items = []
    for name in request.form.getlist("name"):
        if catalog.resolve(footage_dir, name) is None:
            continue
        out_dir = catalog.workspace_for(workspace_dir, name)
        index_payload = extract.load_index(out_dir)
        selected = sorted(data["videos"].get(name, {}).get("selected") or [])
        if index_payload and selected:
            items.append((name, index_payload, selected, out_dir / "full"))
    if not items:
        abort(409, "none of the clips you picked have frames selected")

    # ponytail: one fixed path, rewritten per download. Two downloads at the same
    # moment would clobber each other; this app serves one local user.
    dest = pathlib.Path(workspace_dir) / "export.zip"
    counts = export.build_many(items, dest)
    if not counts:
        abort(409, "selected frames are missing from the cache; re-extract")

    with _notebook_lock:
        fresh = progress.load(progress_path)
        for name, _, selected, _ in items:
            if name in counts:
                progress.entry(fresh, name).setdefault("downloads", []).append(
                    {"at": progress.now_iso(), "count": counts[name], "frames": selected[:]})
        progress.save(progress_path, fresh)

    return send_file(dest, as_attachment=True, mimetype="application/zip",
                     download_name=export.bundle_name(sum(counts.values()), len(counts)))


@app.route("/video/<path:name>")
def video(name: str):
    _video_or_404(name)
    footage_dir, workspace_dir, progress_path = _paths()
    data = progress.load(progress_path)
    record = data["videos"].get(name, {})
    index_payload = extract.load_index(catalog.workspace_for(workspace_dir, name))
    meta = (index_payload or {}).get("meta") or extract.probe(footage_dir / name)

    return render_template(
        "frames.html", name=name, meta=meta,
        frames=(index_payload or {}).get("frames") or [],
        interval=(index_payload or {}).get("interval_s") or DEFAULT_INTERVAL_S,
        selected=sorted(record.get("selected") or []),
        downloads=list(reversed(record.get("downloads") or [])),
        state=progress.state_of(record), job=_job(name),
        default_interval=DEFAULT_INTERVAL_S,
    )


@app.post("/video/<path:name>/extract")
def start_extract(name: str):
    video_path = _video_or_404(name)
    _, workspace_dir, progress_path = _paths()
    try:
        interval = float(request.form.get("interval", DEFAULT_INTERVAL_S))
    except ValueError:
        interval = DEFAULT_INTERVAL_S
    interval = min(extract.MAX_INTERVAL_S, max(extract.MIN_INTERVAL_S, interval))

    running = _job(name)
    if running and running.get("status") == "running":
        return redirect(url_for("video", name=name))

    out_dir = catalog.workspace_for(workspace_dir, name)
    _set_job(name, status="running", done=0, total=0, error=None, interval=interval)

    def work():
        try:
            def report(done, total):
                _set_job(name, done=done, total=total)

            frames = extract.extract(video_path, out_dir, interval, on_progress=report)
            with _notebook_lock:
                data = progress.load(progress_path)
                record = progress.entry(data, name)
                keep = {f["frame"] for f in frames}
                before = list(record.get("selected") or [])
                # Re-extracting at a new interval changes which frames exist. Keep
                # the picks that survived rather than silently pointing at ghosts.
                record["selected"] = sorted(f for f in before if f in keep)
                record["meta"] = extract.probe(video_path)
                record["extract"] = {"interval_s": interval, "count": len(frames),
                                     "at": progress.now_iso()}
                progress.save(progress_path, data)
                dropped = len(before) - len(record["selected"])
            _set_job(name, status="done", done=len(frames), total=len(frames),
                     dropped=dropped)
        except Exception as exc:                       # surfaced in the UI, not swallowed
            traceback.print_exc()
            _set_job(name, status="error", error=f"{type(exc).__name__}: {exc}")

    threading.Thread(target=work, daemon=True, name=f"extract-{name}").start()
    return redirect(url_for("video", name=name))


@app.get("/video/<path:name>/extract/status")
def extract_status(name: str):
    _video_or_404(name)
    return jsonify(_job(name) or {"status": "idle"})


@app.post("/video/<path:name>/selection")
def save_selection(name: str):
    """Autosave. Called on every click, so it must be cheap and idempotent."""
    _video_or_404(name)
    _, workspace_dir, progress_path = _paths()
    payload = request.get_json(silent=True) or {}
    try:
        wanted = {int(v) for v in payload.get("selected", [])}
    except (TypeError, ValueError):
        abort(400, "selected must be a list of integers")

    index_payload = extract.load_index(catalog.workspace_for(workspace_dir, name))
    if index_payload is None:
        abort(409, "no frames extracted for this video yet")
    # Only ever store frame numbers that actually exist on disk.
    valid = sorted(wanted & {f["frame"] for f in index_payload["frames"]})

    with _notebook_lock:
        data = progress.load(progress_path)
        progress.entry(data, name)["selected"] = valid
        progress.save(progress_path, data)
        total = progress.total_selected(data)
        target = max(1, int(data.get("target_frames") or progress.DEFAULT_TARGET))
    return jsonify(saved=len(valid), total_selected=total, target=target)


@app.get("/video/<path:name>/zip")
def download_zip(name: str):
    _video_or_404(name)
    _, workspace_dir, progress_path = _paths()
    out_dir = catalog.workspace_for(workspace_dir, name)
    index_payload = extract.load_index(out_dir)
    if index_payload is None:
        abort(409, "no frames extracted for this video yet")

    data = progress.load(progress_path)
    selected = sorted(data["videos"].get(name, {}).get("selected") or [])
    if not selected:
        abort(409, "nothing selected")

    dest = out_dir / "export.zip"
    written = export.build(index_payload, selected, out_dir / "full", dest)
    if not written:
        abort(409, "selected frames are missing from the cache; re-extract")

    with _notebook_lock:
        fresh = progress.load(progress_path)
        record = progress.entry(fresh, name)
        record.setdefault("downloads", []).append(
            {"at": progress.now_iso(), "count": written, "frames": selected[:]})
        progress.save(progress_path, fresh)

    return send_file(dest, as_attachment=True, mimetype="application/zip",
                     download_name=export.zip_name(name, written))


@app.get("/video/<path:name>/<any(thumb, full):kind>/<path:filename>")
def frame_image(name: str, kind: str, filename: str):
    _video_or_404(name)
    _, workspace_dir, _ = _paths()
    out_dir = catalog.workspace_for(workspace_dir, name)
    # filename comes from the URL. send_from_directory would reject a traversal
    # on its own, but extract.thumb_path joins the name first, so check here.
    if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
        abort(404)
    if kind == "thumb":
        # Caches extracted before THUMB_WIDTH rose hold 320px thumbnails, which
        # the grid would upscale into a blur. Rebuilt once, from the full frame
        # already on disk, the first time the browser asks.
        extract.thumb_path(out_dir, filename)
    return send_from_directory(out_dir / kind, filename, max_age=3600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Not 5000: macOS AirPlay Receiver (ControlCenter) holds [::1]:5000, so a
    # browser resolving localhost to IPv6 gets its 403 instead of this app.
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", default="127.0.0.1",
                        help="localhost only by default; there is no auth")
    parser.add_argument("--footage", type=pathlib.Path, default=FOOTAGE_DIR)
    args = parser.parse_args()

    app.config["FOOTAGE_DIR"] = args.footage.resolve()
    app.config["FOOTAGE_DIR"].mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"footage : {app.config['FOOTAGE_DIR']}")
    print(f"notebook: {PROGRESS_PATH}")
    print(f"open    : http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
