"""sign_v3 glue, without the models: the crop matches run.py's byte for byte,
and every box M1 found comes out tagged with how far down the chain it got.

Only ``stage == "shown"`` may ever be announced. The detector no longer drops
the others -- the preview draws them -- so the guard that used to live here is
now test_signs.py::test_only_shown_stage_is_published."""
import numpy as np
import pytest

Image = pytest.importorskip("PIL.Image")

from signs.v3 import READABLE, V3Detector, square_crop


def run_py_square(im, x1, y1, x2, y2, size):
    """adas/experiments/central/sign_v3/run.py's square(), verbatim."""
    half = min(max(x2 - x1, y2 - y1) / 2, im.width / 2, im.height / 2)
    cx = min(max((x1 + x2) / 2, half), im.width - half)
    cy = min(max((y1 + y2) / 2, half), im.height - half)
    return im.crop((round(cx - half), round(cy - half),
                    round(cx + half), round(cy + half))).resize(
                        (size, size), Image.LANCZOS)


@pytest.mark.parametrize("box", [(10, 10, 50, 90), (0, 0, 5, 5), (600, 450, 700, 500),
                                 (100, 100, 101, 101), (300.4, 200.6, 340.2, 251.7)])
def test_square_crop_is_run_py_square(box):
    rng = np.random.default_rng(0)
    bgr = rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)     # noise: flat grey would pass anything
    ref = run_py_square(Image.fromarray(bgr[..., ::-1]), *box, 128)
    assert np.array_equal(square_crop(bgr, box, 128), np.asarray(ref))


def det(w, h=None):
    h = w if h is None else h
    return {"name": "sign", "box": (100.0, 100.0, 100.0 + w, 100.0 + h), "score": 0.5}


class M1:
    def __init__(self, boxes):
        self.boxes = boxes

    def detect(self, frame):
        return self.boxes


class LaggedM1(M1):
    def __init__(self, boxes):
        super().__init__(boxes)
        self.queue = []

    def push(self, frame):
        self.queue.append(frame)
        return None if len(self.queue) < 2 else (self.queue.pop(0), self.boxes)


class M2:
    size = 128
    displayed = {"stop", "speed_limit", "information"}

    def __init__(self, names):
        self.names = list(names)
        self.seen = 0

    def classify(self, crops):
        self.seen += len(crops)
        return [(self.names.pop(0), 0.9) for _ in crops]


FRAME = np.zeros((480, 640, 3), np.uint8)


def test_small_boxes_never_reach_m2():
    """The point of READABLE: M2 is asked about one box, not two."""
    m2 = M2(["stop"])
    out = V3Detector(M1([det(READABLE - 1), det(READABLE, 60)]), m2).detect(FRAME)
    assert m2.seen == 1
    assert [(d["name"], d["stage"]) for d in out] == [("too_small", "m1_only"), ("stop", "shown")]


def test_every_box_comes_out_tagged_by_stage():
    m2 = M2(["not_a_sign", "other_warning", "speed_limit", "information"])
    out = V3Detector(M1([det(40)] * 4), m2).detect(FRAME)
    # information is a displayed class but classes.IGNORED drops it, so the
    # driver never hears it: green would be a lie. It must come out quiet.
    assert [(d["name"], d["stage"]) for d in out] == [
        ("not_a_sign", "other"), ("other_warning", "other"),
        ("speed_limit", "shown"), ("information", "v3_quiet")]
    assert [d["score"] for d in out] == [0.9] * 4


def test_pipelined_m1_hands_its_older_frame_on():
    a, b = np.zeros_like(FRAME), np.ones_like(FRAME)
    v3 = V3Detector(LaggedM1([det(40)]), M2(["stop"]))
    assert v3.push(a) is None
    frame, out = v3.push(b)
    assert frame is a and out[0]["name"] == "stop"
