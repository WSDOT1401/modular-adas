"""Unit tests for the departure decision state machine — pure logic, no hardware."""
from lane.departure import DepartureDecider


def _decider():
    return DepartureDecider(depart_offset=0.75, raise_frames=3, clear_frames=5)


def test_no_warning_when_centered():
    d = _decider()
    decision = None
    for _ in range(10):
        decision = d.update(0.0)
    assert not decision.active
    assert decision.direction == "none"


def test_raises_only_after_consecutive_frames():
    d = _decider()
    assert not d.update(-0.9).active   # 1 over-threshold frame
    assert not d.update(-0.9).active   # 2 — still not (needs 3)
    decision = d.update(-0.9)          # 3rd consecutive trips it
    assert decision.active
    assert decision.direction == "left"


def test_right_drift_direction():
    d = _decider()
    decision = None
    for _ in range(3):
        decision = d.update(0.9)
    assert decision.active
    assert decision.direction == "right"


def test_single_noisy_frame_does_not_flicker():
    d = _decider()
    d.update(0.9)                      # one bad frame
    decision = d.update(0.0)           # back to safe immediately
    assert not decision.active


def test_clears_only_after_enough_safe_frames():
    d = _decider()
    for _ in range(3):
        d.update(-0.9)                 # raise
    assert d.update(-0.9).active
    for _ in range(4):                 # 4 safe frames — not yet (needs 5)
        assert d.update(0.0).active
    assert not d.update(0.0).active    # 5th clears it


def test_none_offset_treated_as_safe():
    d = _decider()
    for _ in range(3):
        d.update(-0.9)
    assert d.update(-0.9).active
    for _ in range(5):
        d.update(None)                 # no lane detected -> safe
    assert not d.update(None).active
