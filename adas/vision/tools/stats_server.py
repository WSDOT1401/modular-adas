#!/usr/bin/env python3
"""The stats screen's figures and video over the network, so the screen can
be a window on another machine (a Mac beside the car) and the Pi only drives
the round screen. Run this on the Pi, and on the other machine:

    python3 tools/stats_window.py --pi <the Pi's address> --windowed

  GET /stats          what tools/stats_window.py shows (its snapshot(): the
                      vision service's figures, the Pi's power and SoC
                      temperature, the GPS fix), as JSON. Every age is judged
                      here, so the two machines' clocks needn't agree.
  GET /frame?w=W&h=H  the newest preview frame (runtime/preview.py), fitted in
                      W x H, as a JPEG; 204 while there's none. Each request
                      asks the vision service for frames a few seconds more,
                      so nothing is drawn while nobody watches.

JPEG, not the PPM preview.py writes: at 900 x 500 that's 1.4 MB a frame,
20 MB/s at 15 frames a second, more than a phone's hotspot carries; as a
JPEG it's ~70 KB. Anyone on the same network can read these; nothing can be
written.

    ~/adas-venv/bin/python tools/stats_server.py          # port 8090 (--port)
    python tools/stats_server.py --selfcheck              # no Pi needed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats_window as sw  # noqa: E402   # its readers, paths and port: one place for both ends

QUALITY = 80
_jpeg: Tuple[float, Optional[bytes]] = (0.0, None)   # (frame mtime, JPEG): encode each frame once


def ask(w: int, h: int) -> None:
    """Keep the vision service drawing at w x h (preview.py bounds-checks it).
    In one step, so it never reads a half-written request."""
    try:
        tmp = sw.WANT_FILE.with_suffix(".tmp")
        tmp.write_text(f"{w} {h}\n")
        os.replace(tmp, sw.WANT_FILE)
    except OSError:
        pass


def jpeg() -> Optional[bytes]:
    """The newest fresh preview frame as a JPEG, or None."""
    global _jpeg
    mtime = sw.StatsWindow.fresh_frame()
    if mtime is None:
        return None
    if mtime != _jpeg[0]:
        import cv2  # type: ignore

        frame = cv2.imread(str(sw.FRAME_FILE))       # replaced in one step: never half a frame
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY]) \
            if frame is not None else (False, None)
        _jpeg = (mtime, buf.tobytes() if ok else None)
    return _jpeg[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/stats":
            return self.reply(json.dumps(sw.snapshot()).encode(), "application/json")
        if url.path != "/frame":
            return self.send_error(404)
        q = parse_qs(url.query)
        try:
            ask(int(q["w"][0]), int(q["h"][0]))
        except (KeyError, ValueError):
            return self.send_error(400, "want /frame?w=..&h=..")
        body = jpeg()
        if body is None:
            self.send_response(204)
            self.end_headers()
            return
        self.reply(body, "image/jpeg")

    def reply(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass                                          # 15 requests a second would bury the log


def main() -> int:
    ap = argparse.ArgumentParser(description="the stats screen's data, for a window on another machine")
    ap.add_argument("--port", type=int, default=sw.PORT)
    ap.add_argument("--all-cores", action="store_true",
                    help="don't keep off the display's cores (config.DISPLAY_CORES)")
    ap.add_argument("--selfcheck", action="store_true", help="serve fake files to itself and quit")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return 0
    # The JPEG encoding is real work: off the display's cores, below it in
    # priority, like the vision service (runtime/priority.py).
    if not args.all_cores:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import config
        from runtime.priority import yield_to_display
        print(f"stats server: {yield_to_display(config.DISPLAY_CORES, config.VISION_NICE)}",
              flush=True)
    server = ThreadingHTTPServer(("", args.port), Handler)
    print(f"stats server: http://<this Pi>:{args.port}/stats and /frame", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _selfcheck() -> None:
    """Both ends against fake files: the server's answers, and the window's
    Remote reading them (everything but GTK)."""
    import tempfile
    import threading
    import time
    import urllib.error
    import urllib.request

    import cv2  # type: ignore
    import numpy as np  # type: ignore

    tmp = Path(tempfile.mkdtemp())
    for name in ("STATS_FILE", "FRAME_FILE", "WANT_FILE", "GPS_FILE"):
        setattr(sw, name, tmp / getattr(sw, name).name)
    sw.STATS_FILE.write_text(json.dumps({"time": time.time(), "fps": 28.9, "hat_load": 0.5}))
    sw.GPS_FILE.write_text(json.dumps({"fix": True, "mode": "3D", "sats_used": 9,
                                       "sats_in_view": 13, "speed_kmh": 47.2}))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path: str) -> Tuple[int, bytes]:
        try:
            with urllib.request.urlopen(base + path, timeout=2) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    snap = json.loads(get("/stats")[1])
    assert snap["stats"]["fps"] == 28.9 and snap["gps"]["sats_used"] == 9, snap
    assert get("/frame?w=903&h=508") == (204, b""), "no frame yet: 204"
    assert sw.WANT_FILE.read_text() == "903 508\n", "a frame request must ask the vision service"
    assert get("/frame")[0] == 400 and get("/nope")[0] == 404

    cv2.imwrite(str(sw.FRAME_FILE), np.full((508, 903, 3), (138, 208, 79), np.uint8))
    status, body = get("/frame?w=903&h=508")
    assert status == 200 and body[:2] == b"\xff\xd8", "a frame must come back as a JPEG"
    assert len(body) < 100_000, len(body)
    back = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    assert back.shape == (508, 903, 3) and abs(int(back[250, 450, 1]) - 208) < 8, "same picture"

    remote = sw.Remote(f"127.0.0.1:{server.server_address[1]}")
    remote.size = (903, 508)
    for _ in range(50):
        if remote.snap and remote.frame:
            break
        time.sleep(0.1)
    assert remote.snap.get("gps", {}).get("speed_kmh") == 47.2, remote.snap
    assert remote.frame and remote.frame[0][:2] == b"\xff\xd8", "the window's side must get the JPEG"
    assert sw.gps_text(remote.snap["gps"])[0] == "GPS 3D fix  ·  9/13 sats  ·  47 km/h"
    assert sw.gps_text(None)[0] == "GPS --"
    server.shutdown()
    print("ok: /stats, /frame (204, JPEG, asks for frames), 400/404; the window's Remote reads both")


if __name__ == "__main__":
    raise SystemExit(main())
