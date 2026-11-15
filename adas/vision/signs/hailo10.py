"""b01 on the Pi's AI HAT+ 2 (Hailo-10H), fed as fast as the chip takes it.

The compiled model (``central/b01_hailo_model/``, from tools/export_hailo.py)
is multi-context, so one frame at a time spends most of its ~55 ms waiting
for the chip to swap contexts: 18 fps. With a few frames in flight the
swaps overlap and the chip does ~60 fps. So :meth:`HailoSignDetector.push`
hands a frame to the chip and returns the detections of the frame it sent
``depth`` frames ago, together with that frame (the speed reader crops it).
At 30 fps and depth 3 that's 100 ms behind the camera.

Ultralytics' own Hailo backend isn't used: it goes through HailoRT's older
interface, which the Hailo-10H doesn't implement (HAILO_NOT_IMPLEMENTED), and
on the Pi its per-frame torch pre/post-processing costs more CPU than the
chip time. Here the letterbox is a cv2 pad and the decode is numpy on the
anchors that clear the threshold, matching ultralytics' (b01 is YOLO26 with
the one-to-many head: ltrb distances, sigmoid scores, NMS per class).

btop can't see the HAT, and on the Hailo-10H HailoRT 5.1.1's own
``hailortcli monitor`` shows nothing (not supported there yet). So once a
second this writes the chip's fps, load, latency and temperature to
:data:`STATS_FILE`; ``tools/hat_monitor.py`` shows them live.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np  # type: ignore

_TIMEOUT_MS = 10_000
_PAD = 114          # ultralytics' letterbox grey
_IOU = 0.7          # ultralytics' NMS default
_MAX_DET = 300

STATS_FILE = Path("/dev/shm/adas-hat.json")
# Most the chip does with b01.hef and this many frames in flight (measured on
# the AI HAT+ 2): the "100%" of the load figure.
_MAX_FPS = {1: 18.0, 2: 35.0, 3: 51.0, 4: 59.0}


class HailoSignDetector:
    on_hailo = True

    def __init__(self, folder: str, conf: float = 0.4, depth: int = 3) -> None:
        import yaml  # type: ignore
        from hailo_platform import (HEF, FormatType, HailoSchedulingAlgorithm,  # type: ignore
                                    VDevice)

        hef_file = next(Path(folder).glob("*.hef"), None)
        if hef_file is None:
            raise FileNotFoundError(f"No .hef file in {folder}")
        meta = yaml.safe_load((Path(folder) / "metadata.yaml").read_text())
        self.names = {int(k): v for k, v in meta["names"].items()}
        self._conf = conf
        self._logit = float(np.log(conf / (1 - conf)))   # sigmoid(x) > conf  <=>  x > logit

        # For `hailortcli monitor`, once a HailoRT that supports it on the
        # Hailo-10H is installed (5.1.1 doesn't). Must be set before the VDevice.
        os.environ.setdefault("HAILO_MONITOR", "1")
        self._hef_name = hef_file.name
        hef = HEF(str(hef_file))
        self._size = hef.get_input_vstream_infos()[0].shape[0]       # 1280 (square)
        order = [o.name for o in hef.get_output_vstream_infos()]
        half = len(order) // 2
        self._box_names, self._cls_names = order[:half], order[half:]

        params = VDevice.create_params()
        params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
        self._device = VDevice(params)
        model = self._device.create_infer_model(str(hef_file))
        model.set_batch_size(1)
        model.input().set_format_type(FormatType.UINT8)
        for out in model.outputs:
            out.set_format_type(FormatType.FLOAT32)      # dequantised by HailoRT, off our thread
        shapes = {o.name: o.shape for o in model.outputs}
        self._configured = model.configure()
        self._configured.__enter__()
        self._free = [self._configured.create_bindings(output_buffers={
            n: np.empty(s, dtype=np.float32) for n, s in shapes.items()}) for _ in range(depth)]
        self._depth = depth
        self._inflight: deque = deque()   # (job, bindings, input, frame, scale, pad)
        self._anchors, self._strides = self._make_anchors(shapes)
        self._chips = self._device.get_physical_devices()   # kept: the control dies with it
        self._stats_t, self._stats_n, self._stats_lat = time.monotonic(), 0, 0.0

    def _make_anchors(self, shapes: dict) -> Tuple[np.ndarray, np.ndarray]:
        points, strides = [], []
        for name in self._box_names:
            h, w = shapes[name][:2]
            sy, sx = np.meshgrid(np.arange(h) + 0.5, np.arange(w) + 0.5, indexing="ij")
            points.append(np.stack((sx, sy), -1).reshape(-1, 2))
            strides.append(np.full(h * w, self._size / h, dtype=np.float32))
        return np.concatenate(points).astype(np.float32), np.concatenate(strides)

    # ---- frames in --------------------------------------------------------------
    def _letterbox(self, frame: np.ndarray) -> Tuple[np.ndarray, float, Tuple[int, int]]:
        import cv2  # type: ignore

        h, w = frame.shape[:2]
        r = min(self._size / h, self._size / w)
        if r != 1.0:
            nw, nh = round(w * r), round(h * r)
            frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            h, w = nh, nw
        top, left = (self._size - h) // 2, (self._size - w) // 2
        img = cv2.copyMakeBorder(frame, top, self._size - h - top, left, self._size - w - left,
                                 cv2.BORDER_CONSTANT, value=(_PAD, _PAD, _PAD))
        return np.ascontiguousarray(img[..., ::-1]), r, (left, top)      # BGR -> RGB

    def push(self, frame: np.ndarray) -> "Optional[Tuple[np.ndarray, List[dict]]]":
        """Send a frame to the chip. Returns ``(older_frame, its detections)``
        once ``depth`` frames are in flight, else None (the first few frames)."""
        done = None
        if len(self._inflight) == self._depth:
            done = self._finish(self._inflight.popleft())
        img, r, pad = self._letterbox(frame)
        bindings = self._free.pop()
        bindings.input().set_buffer(img)
        self._configured.wait_for_async_ready(timeout_ms=_TIMEOUT_MS)
        done_at: list = []                    # set by HailoRT's thread when the chip is done
        sent = time.monotonic()
        job = self._configured.run_async(
            [bindings], lambda completion_info: done_at.append(time.monotonic()))
        self._inflight.append((job, bindings, img, frame, r, pad, sent, done_at))
        return done

    def detect(self, frame: np.ndarray) -> "List[dict]":
        """One frame, waiting for its result (no pipelining)."""
        while self._inflight:
            self._finish(self._inflight.popleft())
        self.push(frame)
        return self._finish(self._inflight.popleft())[1]

    # ---- detections out ---------------------------------------------------------
    def _finish(self, item) -> "Tuple[np.ndarray, List[dict]]":
        job, bindings, _img, frame, r, pad, sent, done_at = item
        job.wait(_TIMEOUT_MS)
        self._stats_n += 1
        self._stats_lat += (done_at[0] if done_at else time.monotonic()) - sent
        self._write_stats()
        logits = np.concatenate([bindings.output(n).get_buffer().reshape(-1, len(self.names))
                                 for n in self._cls_names])
        dist = np.concatenate([bindings.output(n).get_buffer().reshape(-1, 4)
                               for n in self._box_names])
        self._free.append(bindings)
        return frame, self._decode(logits, dist, r, pad, frame.shape)

    def _decode(self, logits, dist, r, pad, shape) -> "List[dict]":
        import cv2  # type: ignore

        best = logits.max(1)
        keep = np.nonzero(best > self._logit)[0]
        if keep.size == 0:
            return []
        cls = logits[keep].argmax(1)
        score = 1.0 / (1.0 + np.exp(-best[keep]))
        a, s, d = self._anchors[keep], self._strides[keep, None], dist[keep]
        xyxy = np.concatenate((a - d[:, :2], a + d[:, 2:]), 1) * s
        xywh = np.concatenate((xyxy[:, :2], xyxy[:, 2:] - xyxy[:, :2]), 1)
        idx = cv2.dnn.NMSBoxesBatched(xywh.tolist(), score.tolist(), cls.tolist(),
                                      self._conf, _IOU)
        idx = np.asarray(idx, dtype=int).reshape(-1)[:_MAX_DET]
        h, w = shape[:2]
        out = []
        for i in idx[np.argsort(-score[idx])]:
            x0, y0, x1, y1 = xyxy[i]
            x0, x1 = (np.clip((v - pad[0]) / r, 0, w) for v in (x0, x1))
            y0, y1 = (np.clip((v - pad[1]) / r, 0, h) for v in (y0, y1))
            out.append({"name": self.names[int(cls[i])], "box": (float(x0), float(y0), float(x1), float(y1)),
                        "score": float(score[i])})
        return out

    # ---- stats for tools/hat_monitor.py -------------------------------------------
    def _write_stats(self) -> None:
        now = time.monotonic()
        span = now - self._stats_t
        if span < 1.0:
            return
        fps = self._stats_n / span
        cap = _MAX_FPS.get(self._depth)
        try:
            t = self._chips[0].control.get_chip_temperature()
            temp = round(max(t.ts0_temperature, t.ts1_temperature), 1)
        except Exception:            # noqa: BLE001 - a missed reading isn't worth a crash
            temp = None
        stats = {
            "time": time.time(), "pid": os.getpid(), "model": self._hef_name,
            "fps": round(fps, 1), "max_fps": cap,
            "load": round(min(fps / cap, 1.0), 3) if cap else None,
            "latency_ms": round(self._stats_lat / self._stats_n * 1000, 1) if self._stats_n else None,
            "in_flight": len(self._inflight), "depth": self._depth, "temp_c": temp,
        }
        self._stats_t, self._stats_n, self._stats_lat = now, 0, 0.0
        try:
            tmp = STATS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(stats))
            os.replace(tmp, STATS_FILE)
        except OSError:
            pass

    def close(self) -> None:
        while self._inflight:
            self._inflight.popleft()[0].wait(_TIMEOUT_MS)
        self._configured.__exit__(None, None, None)
        self._device.release()
        try:
            STATS_FILE.unlink()
        except OSError:
            pass
