"""Frame scheduler: capture -> stages (signs, lane) -> publish.

The orchestration spine of the vision service. Each frame it pushes one UDP
datagram with:

  - ``module_status`` and ``system_fault`` every time: the display's heartbeat
    (without ADAS keys for 3 s it treats the ADAS as not running) and its
    feature icons;
  - whatever the enabled stages decided (``sign_seen``, ``speed_limit``,
    ``lane_*``).

Stages come from ``config.STAGES``. Signs run today; lane is wired but its
CV stages are still TODO. Forward collision is not built yet, so its icon
reads "off".
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from adas_protocol import MODULE_STATUS, SYSTEM_FAULT

import config
from capture.base import FrameSource
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

    # ---- stages ---------------------------------------------------------------
    def _build_signs(self):
        from signs.detector import SignDetector
        from signs.pipeline import SignPipeline
        from signs.tracker import SignTracker

        if not Path(config.SIGN_WEIGHTS).is_file():
            sys.exit(f"sign detector weights not found: {config.SIGN_WEIGHTS}\n"
                     "copy b01.pt there (see adas/experiments/central/README.md) or pass --weights")
        detector = SignDetector(config.SIGN_WEIGHTS, config.SIGN_IMGSZ, config.SIGN_CONF,
                                config.SIGN_DEVICE)
        reader = vote = None
        if Path(config.SPEED_READER).is_file():
            from signs.speed import load_reader
            reader, vote = load_reader(config.SPEED_READER, config.SPEED_READER_CODE)
        else:
            print(f"speed reader not found at {config.SPEED_READER}: "
                  "speed limits will be announced without a number", file=sys.stderr)
        tracker = SignTracker(config.SIGN_CONFIRM_FRAMES, config.SIGN_GAP_FRAMES)
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
                "lane": "on" if self._lane else "off",
                "fcw": "off",
                "signs": "on" if self._signs else "off",
            },
            SYSTEM_FAULT: "",
        }

    # ---- loop -----------------------------------------------------------------
    def run(self) -> None:
        frames = 0
        started = time.monotonic()
        try:
            for frame in self._source.frames():
                payload = self._status()
                detections = []
                if self._signs is not None:
                    events, detections = self._signs.update(frame)
                    payload.update(events)
                    self._log(events)
                if self._lane is not None:
                    payload.update(self._lane(frame))
                self._publisher.send(payload)
                frames += 1
                if self._preview and not self._show(frame, detections):
                    break
        finally:
            elapsed = max(time.monotonic() - started, 1e-6)
            print(f"{frames} frames in {elapsed:.0f} s ({frames / elapsed:.1f} fps), "
                  f"{self._source.dropped} dropped to keep up", file=sys.stderr)
            self._source.close()
            self._publisher.close()
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
