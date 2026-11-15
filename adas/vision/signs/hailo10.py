"""Make ultralytics' Hailo backend work on the AI HAT+ 2 (Hailo-10H).

Ultralytics loads a .hef through HailoRT's older interface (configure a
network group, then InferVStreams). The Hailo-10H doesn't implement that
(libhailort error 7, HAILO_NOT_IMPLEMENTED); it only takes the newer
InferModel interface. :func:`patch` swaps the loading step for one that uses
InferModel and keeps the rest of the backend, so pre- and post-processing
(letterbox, box decoding, NMS) are still ultralytics' own and the results
match the .pt model's.

The Hailo-8/8L understand both interfaces, so the patch is harmless there.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np  # type: ignore

_TIMEOUT_MS = 10_000


class _Runner:
    """InferModel wrapped in the ``infer({input: batch}) -> {output: batch}``
    call the ultralytics backend makes on its InferVStreams."""

    def __init__(self, hef_path: str) -> None:
        from hailo_platform import FormatType, HailoSchedulingAlgorithm, VDevice  # type: ignore

        params = VDevice.create_params()
        params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
        self._device = VDevice(params)
        model = self._device.create_infer_model(hef_path)
        model.set_batch_size(1)
        model.input().set_format_type(FormatType.UINT8)
        for out in model.outputs:
            out.set_format_type(FormatType.FLOAT32)       # dequantised on the way out
        self._model = model
        self._configured = model.configure()
        self._configured.__enter__()
        self._outputs = {o.name: o.shape for o in model.outputs}
        self._bindings = self._configured.create_bindings(output_buffers={
            name: np.empty(shape, dtype=np.float32) for name, shape in self._outputs.items()})

    def infer(self, inputs: dict) -> dict:
        (batch,) = inputs.values()
        results = {name: [] for name in self._outputs}
        for frame in batch:
            self._bindings.input().set_buffer(np.ascontiguousarray(frame))
            self._configured.run([self._bindings], _TIMEOUT_MS)
            for name in self._outputs:
                results[name].append(self._bindings.output(name).get_buffer().copy())
        return {name: np.stack(frames) for name, frames in results.items()}

    def close(self) -> None:
        self._configured.__exit__(None, None, None)
        self._device.release()


def _load_model(self, weight) -> None:
    from hailo_platform import HEF  # type: ignore

    hef_file = next(Path(weight).rglob("*.hef"), None)
    if hef_file is None:
        raise FileNotFoundError(f"No .hef file found in: {weight}")
    self.apply_metadata(self.read_metadata(hef_file))
    hef = HEF(str(hef_file))
    self.input_info = hef.get_input_vstream_infos()[0]
    self.output_infos = hef.get_output_vstream_infos()      # the order the decoders expect
    self.model = _Runner(str(hef_file))
    self._anchors = None
    if self.task in {"segment", "pose", "obb"}:
        from ultralytics.nn.modules import DFL  # type: ignore

        self._dfl = DFL()
    self.end2end = self.end2end or self.metadata.get("nms", False)


def _del(self) -> None:
    if isinstance(getattr(self, "model", None), _Runner):
        self.model.close()


def patch() -> None:
    """Route ultralytics' Hailo backend through InferModel. Call before YOLO()."""
    from ultralytics.nn.backends.hailo import HailoBackend  # type: ignore

    HailoBackend.load_model = _load_model
    HailoBackend.__del__ = _del
