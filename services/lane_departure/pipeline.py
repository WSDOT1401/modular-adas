"""Lane-departure pipeline: capture -> preprocess -> detect -> decide -> publish.

The orchestration spine. The CV stages (capture/preprocess/detector) are still
TODO, but the decision + publish path is real, so the moment those land the
whole thing runs end-to-end. Until then, use tools/mock_lane_writer.py to
exercise the cluster's alert UI.
"""
from __future__ import annotations

from w124_protocol import UdpPublisher

import config
import detector
import preprocess
from capture import FrameSource
from departure import DepartureDecider


class LaneDeparturePipeline:
    def __init__(self) -> None:
        self._source = FrameSource(
            config.SOURCE, config.FRAME_WIDTH, config.FRAME_HEIGHT, config.CLIP_PATH
        )
        self._decider = DepartureDecider(
            config.DEPART_OFFSET, config.RAISE_FRAMES, config.CLEAR_FRAMES
        )
        self._publisher = UdpPublisher(config.UDP_HOST, config.UDP_PORT)

    def run(self) -> None:
        try:
            for frame in self._source.frames():
                masked = preprocess.region_of_interest(frame)
                edges = preprocess.edges(masked)
                offset = detector.lane_offset(edges)
                decision = self._decider.update(offset)
                self._publisher.send(decision.to_payload())
        finally:
            self._source.close()
            self._publisher.close()
