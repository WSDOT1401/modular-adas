"""Sign stage logic, without the models: a scripted detector and reader stand
in for b01 and the speed reader, so this runs anywhere (no torch, no weights).
"""
from signs.classes import publishable
from signs.pipeline import SignPipeline
from signs.tracker import SignTracker


def box(name, width=40):
    return {"name": name, "box": (100.0, 100.0, 100.0 + width, 100.0 + width), "score": 0.8}


class ScriptedDetector:
    """Returns the next frame's detections from a list, then nothing."""

    def __init__(self, frames):
        self.frames = list(frames)

    def detect(self, frame):
        return self.frames.pop(0) if self.frames else []


class FixedReader:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self, frame, box):
        self.calls += 1
        return self.value, 0.9


class CountVote:
    """Same contract as SignVote: fires once after `need` readings, rearms on a gap."""

    def __init__(self, need=2, gap=3):
        self.need, self.gap = need, gap
        self.n = self.idle = 0
        self.fired = False

    def update(self, value):
        if value is None:
            self.idle += 1
            if self.idle > self.gap:
                self.n, self.fired = 0, False
            return None
        self.idle = 0
        self.n += 1
        if self.n >= self.need and not self.fired:
            self.fired = True
            return value
        return None


def run(pipeline, n):
    return [pipeline.update(None)[0] for _ in range(n)]


# ---- tracker ----------------------------------------------------------------

def test_tracker_fires_once_after_confirm_frames():
    t = SignTracker(confirm_frames=3, gap_frames=5)
    assert t.update(["stop"]) == []
    assert t.update(["stop"]) == []
    assert t.update(["stop"]) == ["stop"]
    assert t.update(["stop"]) == []            # same sign, still in view


def test_tracker_tolerates_missed_frames():
    # b01 finds a sign in about one frame in three: gaps must not reset it.
    t = SignTracker(confirm_frames=3, gap_frames=5)
    seen = [t.update(f) for f in (["stop"], [], ["stop"], [], [], ["stop"])]
    assert seen[-1] == ["stop"]


def test_tracker_rearms_after_the_sign_has_gone():
    t = SignTracker(confirm_frames=2, gap_frames=3)
    assert [t.update(["stop"]) for _ in range(2)] == [[], ["stop"]]
    for _ in range(4):
        t.update([])                            # gone for longer than the gap
    assert [t.update(["stop"]) for _ in range(2)] == [[], ["stop"]]


def test_catch_all_classes_are_not_published():
    assert not publishable("other_regulatory")
    assert not publishable("information")
    assert publishable("pedestrian_crossing")


# ---- pipeline ---------------------------------------------------------------

def test_new_sign_is_sent_once():
    det = ScriptedDetector([[box("pedestrian_crossing")]] * 5)
    out = run(SignPipeline(det, tracker=SignTracker(3, 5)), 5)
    assert out == [{}, {}, {"sign_seen": "pedestrian_crossing"}, {}, {}]


def test_catch_all_detections_never_reach_the_display():
    det = ScriptedDetector([[box("other_warning")]] * 5)
    assert run(SignPipeline(det, tracker=SignTracker(2, 5)), 5) == [{}] * 5


def test_speed_limit_rings_first_then_sends_the_number():
    det = ScriptedDetector([[box("speed_limit")]] * 4)
    pipe = SignPipeline(det, FixedReader(80), CountVote(need=3), SignTracker(2, 5))
    out = run(pipe, 4)
    assert out[1] == {"sign_seen": "speed_limit"}                      # confirmed: ring the limit
    assert out[2] == {"speed_limit": 80, "sign_seen": "speed_limit"}   # number settled
    assert out[3] == {}


def test_unreadable_limit_is_announced_without_a_number():
    det = ScriptedDetector([[box("speed_limit")]] * 4)
    pipe = SignPipeline(det, FixedReader(None), CountVote(need=2), SignTracker(2, 5))
    out = run(pipe, 4)
    assert {"sign_seen": "speed_limit"} in out
    assert not any("speed_limit" in o and o.get("speed_limit") for o in out if "speed_limit" in o)


def test_reader_gets_the_nearest_speed_limit_box():
    seen = []

    class Reader:
        def __call__(self, frame, b):
            seen.append(b[2] - b[0])
            return 60, 0.9

    det = ScriptedDetector([[box("speed_limit", 30), box("speed_limit", 70)]])
    SignPipeline(det, Reader(), CountVote(), SignTracker(3, 5)).update(None)
    assert seen == [70]


def test_pipelined_detector_reads_the_frame_its_detections_came_from():
    # The AI HAT's detector answers `lag` frames late and hands that frame back.
    class LaggedDetector:
        def __init__(self, lag):
            self.lag, self.queue = lag, []

        def push(self, frame):
            self.queue.append(frame)
            if len(self.queue) <= self.lag:
                return None
            old = self.queue.pop(0)
            return old, [box("speed_limit")]

    read = []

    class Reader:
        def __call__(self, frame, b):
            read.append(frame)
            return 40, 0.9

    pipe = SignPipeline(LaggedDetector(2), Reader(), CountVote(need=2), SignTracker(2, 5))
    out = [pipe.update(f"frame{i}")[0] for i in range(5)]
    assert out[:2] == [{}, {}]                     # filling up
    assert read == ["frame0", "frame1", "frame2"]
    assert out[3] == {"speed_limit": 40, "sign_seen": "speed_limit"}


def test_two_new_signs_in_one_frame_go_out_one_per_datagram():
    det = ScriptedDetector([[box("stop"), box("u_turn")]] * 2)
    out = run(SignPipeline(det, tracker=SignTracker(2, 5)), 3)
    assert out[1] == {"sign_seen": "stop"}
    assert out[2] == {"sign_seen": "u_turn"}


def test_tracker_holds_a_repeat_back_while_the_car_waits():
    # Stopped at a light, a distant sign drops out of view and back again.
    clock = [0.0]
    t = SignTracker(confirm_frames=2, gap_frames=3, repeat_s=20, clock=lambda: clock[0])

    def visit():
        out = []
        for _ in range(2):
            clock[0] += 0.1
            out += t.update(["pedestrian_crossing"])
        for _ in range(4):
            clock[0] += 0.1
            t.update([])
        return out

    assert visit() == ["pedestrian_crossing"]
    assert visit() == []                         # same sign, seconds later: quiet
    clock[0] += 20
    assert visit() == ["pedestrian_crossing"]    # a new one, well down the road


def test_only_shown_stage_is_published():
    """The preview gets every box; the driver only ever hears about "shown".

    v3.py stopped filtering so the live view can draw what M1 found. If this
    breaks, the dash starts announcing classes it is configured never to show.
    """
    tagged = [dict(box("speed_limit"), stage="shown"),
              dict(box("pedestrian_crossing"), stage="other"),
              dict(box("information"), stage="v3_quiet"),
              dict(box("too_small"), stage="m1_only")]
    pipe = SignPipeline(ScriptedDetector([tagged] * 3), tracker=SignTracker(confirm_frames=3))
    events = [pipe.update(None)[0] for _ in range(3)]
    assert [e.get("sign_seen") for e in events] == [None, None, "speed_limit"]
    # ...and the preview still sees all three
    assert len(pipe.update(None)[1]) == 0        # detector is exhausted now
    seen = SignPipeline(ScriptedDetector([tagged]), tracker=SignTracker()).update(None)[1]
    assert [d["stage"] for d in seen] == ["shown", "other", "v3_quiet", "m1_only"]


def test_untagged_detections_still_publish():
    """b01 (the non-v3 stack) emits no stage field: it must behave as before."""
    frames = [[box("stop")]] * 3
    pipe = SignPipeline(ScriptedDetector(frames), tracker=SignTracker(confirm_frames=3))
    assert [pipe.update(None)[0].get("sign_seen") for _ in range(3)][-1] == "stop"
