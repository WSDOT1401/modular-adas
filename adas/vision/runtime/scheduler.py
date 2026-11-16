"""Frame scheduler: capture -> stages (signs, lane) -> publish.

The orchestration spine of the vision service. Each frame it pushes one UDP
datagram with:

  - ``module_status`` and ``system_fault`` every time: the display's heartbeat
    (without ADAS keys for 3 s it treats the ADAS as not running) and its
    feature icons;
  - whatever the enabled stages decided (``sign_seen``, ``speed_limit``,
    ``lane_*``).

Once a second it also writes its load figures (frame rate, Pi CPU, memory and
temperature, the AI HAT's load and temperature) to ``runtime.health.STATS_FILE``
for ``tools/stats_window.py``, a stats screen of its own: they stay off the
driver's display. While that window is open it also gets what the service
sees, the frame with its boxes (runtime/preview.py).

Stages come from ``config.STAGES``. Signs run today; lane is wired but its
CV stages are still TODO. Forward collision is not built yet, so its icon
reads "off".

The driver switches features on and off from the display's menu; the display
sends ``feature_enable`` to the control port (udp 9102). A switched-off stage
is skipped entirely (no inference, so no CPU spent) and reported as "off".
Until the first message arrives, everything built is on.
"""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from typing import Optional

from adas_protocol import DEFAULT_CONTROL_PORT, FEATURE_ENABLE, MODULE_STATUS, SYSTEM_FAULT

import config
from capture.base import FrameSource
from runtime.health import HealthMonitor, clear_stats, write_stats
from runtime.preview import FramePreview
from runtime.publisher import UdpPublisher


class Scheduler:
    def __init__(self, preview: bool = False) -> None:
        self._source = FrameSource(
            config.SOURCE, config.FRAME_WIDTH, config.FRAME_HEIGHT, config.CLIP_PATH,
            realtime=config.REPLAY_REALTIME, loop=config.REPLAY_LOOP, fps=config.TARGET_FPS,
        )
        self._publisher = UdpPublisher(config.UDP_HOST, config.UDP_PORT)
        self._preview = preview
        self._signs = self._build_signs() if "signs" in config.STAGES else None
        self._lane = self._build_lane() if "lane" in config.STAGES else None
        self._enabled = {"lane": True, "fcw": True, "signs": True}   # the driver's choices
        self._control = self._open_control()
        self._health = HealthMonitor()
        self._stats_at = time.monotonic()
        self._stats_frames = 0
        self._view = FramePreview(config.PREVIEW_FPS)

    # ---- the driver's choices (display -> here) ----------------------------------
    def _open_control(self) -> Optional[socket.socket]:
        port = config.CONTROL_PORT or DEFAULT_CONTROL_PORT
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((config.CONTROL_BIND, port))
        except OSError as e:
            print(f"control port {port} unavailable ({e}): every feature stays on", file=sys.stderr)
            sock.close()
            return None
        sock.setblocking(False)
        return sock

    def _read_control(self) -> None:
        while self._control is not None:
            try:
                data = self._control.recv(4096)
            except (BlockingIOError, OSError):
                return
            try:
                choice = json.loads(data).get(FEATURE_ENABLE)
            except (ValueError, AttributeError):
                continue
            if not isinstance(choice, dict):
                continue
            for name in self._enabled:
                if name in choice and bool(choice[name]) != self._enabled[name]:
                    self._enabled[name] = bool(choice[name])
                    print(f"[{self._source.time:7.1f} s] driver switched {name} "
                          f"{'on' if self._enabled[name] else 'off'}", flush=True)

    def _running(self, name: str, stage) -> bool:
        return stage is not None and self._enabled[name]

    # ---- stages ---------------------------------------------------------------
    def _build_signs(self):
        from signs.detector import SignDetector
        from signs.pipeline import SignPipeline
        from signs.tracker import SignTracker

        def find(weights: str, conf: float):
            """A sign finder: a .pt, or a Hailo model folder (on the AI HAT)."""
            if not Path(weights).exists():
                sys.exit(f"sign model not found: {weights}\n"
                         "see adas/experiments/central/README.md, or pass --weights")
            if Path(weights).is_dir():
                from signs.hailo10 import HailoSignDetector

                return HailoSignDetector(weights, conf, config.SIGN_HAILO_DEPTH)
            return SignDetector(weights, config.SIGN_IMGSZ, conf, config.SIGN_DEVICE)

        def where(model) -> str:
            if getattr(model, "on_hailo", False):
                return "the AI HAT"
            return config.SIGN_DEVICE or "the CPU/GPU"

        if config.SIGN_STACK == "v3":
            from signs.v3 import TorchCropClassifier, V3Detector

            m1 = find(config.V3_M1, config.V3_M1_CONF)
            if Path(config.V3_M2).is_dir():
                from signs.hailo10 import HailoCropClassifier

                m2 = HailoCropClassifier(config.V3_M2)
            else:
                m2 = TorchCropClassifier(config.V3_M2, config.SIGN_DEVICE)
            detector = V3Detector(m1, m2)
            print(f"signs: sign_v3, M1 {Path(config.V3_M1).name} on {where(m1)}, "
                  f"M2 {Path(config.V3_M2).name} on {where(m2)}", file=sys.stderr)
        else:
            detector = find(config.SIGN_WEIGHTS, config.SIGN_CONF)
            print(f"signs: {config.SIGN_WEIGHTS} on {where(detector)}", file=sys.stderr)
        reader = vote = None
        if Path(config.SPEED_READER).is_file():
            from signs.speed import load_reader
            reader, vote = load_reader(config.SPEED_READER, config.SPEED_READER_CODE)
        else:
            print(f"speed reader not found at {config.SPEED_READER}: "
                  "speed limits will be announced without a number", file=sys.stderr)
        tracker = SignTracker(config.SIGN_CONFIRM_FRAMES, config.SIGN_GAP_FRAMES,
                              config.SIGN_REPEAT_S)
        return SignPipeline(detector, reader, vote, tracker)

    def _build_lane(self):
        from lane import detector, preprocess
        from lane.departure import DepartureDecider

        decider = DepartureDecider(config.DEPART_OFFSET, config.RAISE_FRAMES, config.CLEAR_FRAMES)

        def step(frame) -> dict:
            edges = preprocess.edges(preprocess.region_of_interest(frame))
            return decider.update(detector.lane_offset(edges)).to_payload()
        return step

    def _status(self) -> dict:
        return {
            MODULE_STATUS: {
                "lane": "on" if self._running("lane", self._lane) else "off",
                "fcw": "off",                              # not built yet
                "signs": "on" if self._running("signs", self._signs) else "off",
            },
            SYSTEM_FAULT: "",
        }

    def _write_stats(self, frames: int) -> None:
        """Once a second: the load figures, for tools/stats_window.py."""
        now = time.monotonic()
        if now - self._stats_at < 1.0:
            return
        stats = {"fps": round((frames - self._stats_frames) / (now - self._stats_at), 1),
                 "dropped": self._source.dropped, "source": config.SOURCE}
        self._stats_at, self._stats_frames = now, frames
        stats.update(self._health.snapshot().as_dict())
        # Switched off, the signs stage doesn't run, and the HAT's last figures go stale.
        on = self._running("signs", self._signs)
        hat = getattr(self._signs.detector, "stats", None) if on else None
        for key in ("load", "fps", "temp_c", "latency_ms", "max_fps"):
            if hat and hat.get(key) is not None:
                stats["hat_" + key] = hat[key]
        write_stats(stats)

    # ---- loop -----------------------------------------------------------------
    def run(self) -> None:
        frames = 0
        started = time.monotonic()
        try:
            for frame in self._source.frames():
                self._read_control()
                payload = self._status()
                detections, seen = [], frame
                if self._running("signs", self._signs):
                    events, detections = self._signs.update(frame)
                    payload.update(events)
                    self._log(events)
                    # On the AI HAT the boxes are for a frame a few back: draw them on that one.
                    seen = self._signs.frame if self._signs.frame is not None else frame
                if self._running("lane", self._lane):
                    payload.update(self._lane(frame))
                self._publisher.send(payload)
                frames += 1
                self._write_stats(frames)
                self._view.update(seen, detections)
                if self._preview and not self._show(seen, detections):
                    break
        finally:
            elapsed = max(time.monotonic() - started, 1e-6)
            print(f"{frames} frames in {elapsed:.0f} s ({frames / elapsed:.1f} fps), "
                  f"{self._source.dropped} dropped to keep up", file=sys.stderr)
            self._source.close()
            clear_stats()
            self._view.close()
            if self._signs is not None:
                self._signs.close()
            self._publisher.close()
            if self._control is not None:
                self._control.close()
            if self._preview:
                import cv2  # type: ignore
                cv2.destroyAllWindows()

    def _log(self, events: dict) -> None:
        if events:
            print(f"[{self._source.time:7.1f} s] {events}", flush=True)

    def _show(self, frame, detections) -> bool:
        """Draw this frame's boxes in a window. False when the user quits (q/Esc)."""
        import cv2  # type: ignore

        view = frame.copy()
        for d in detections:
            x0, y0, x1, y1 = (int(v) for v in d["box"])
            cv2.rectangle(view, (x0, y0), (x1, y1), (80, 210, 140), 2)
            cv2.putText(view, f"{d['name']} {d['score']:.2f}", (x0, max(0, y0 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 210, 140), 2)
        scale = 960 / view.shape[1] if view.shape[1] > 960 else 1.0
        if scale != 1.0:
            view = cv2.resize(view, None, fx=scale, fy=scale)
        cv2.imshow("adas vision", view)
        return cv2.waitKey(1) & 0xFF not in (ord("q"), 27)
