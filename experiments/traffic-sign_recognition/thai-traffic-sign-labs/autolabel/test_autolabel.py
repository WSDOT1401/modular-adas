"""The check for the autolabel pipeline.

These assert the places where a silent bug would corrupt the dataset without
anything visibly failing -- a box on the wrong frame, a label on the wrong sign.
Everything else here is either obvious or caught by the model simply not loading.

Still to add, once those scripts exist (see README):
  * round trip CVAT export -> crops -> predictions -> CVAT zip keeps every label
    on the box it came from
  * propagate.py writes a track's confirmed label onto every frame of that
    track, and onto no frame of any other track
"""

from __future__ import annotations

import numpy as np
import cv2
import pytest

import track


def _det(frame, tid, cls, side, conf=0.9):
    return {"frame": frame, "track": tid, "cls": cls, "conf": conf,
            "bbox": [10.0, 20.0, side, side], "side": float(side)}


def _track(tid, dets):
    return {"id": tid, "dets": dets, "best": max(dets, key=lambda d: d["side"])}


def test_summarise_trusts_the_closeup_not_the_first_sighting():
    # The same sign called Warning far away and Regulatory up close: the close-up
    # wins, and the disagreement is flagged for review rather than hidden.
    t = _track(7, [_det(0, 7, 1, 17), _det(3, 7, 1, 40), _det(6, 7, 0, 98)])
    out = track.summarise(t)
    assert out["cls"] == 0
    assert out["best_frame"] == 6
    assert out["best_side"] == 98
    assert out["flipped"] is True
    assert out["n_dets"] == 3
    assert (out["span"], out["max_gap"]) == (6, 3)

    # The shape of a merged track: two signs sharing an id, minutes apart.
    merged = track.summarise(_track(9, [_det(0, 9, 0, 30), _det(3, 9, 0, 40), _det(4200, 9, 1, 35)]))
    assert merged["span"] == 4200 and merged["max_gap"] == 4197

    steady = _track(8, [_det(0, 8, 2, 30), _det(3, 8, 2, 60)])
    assert track.summarise(steady)["flipped"] is False


def test_select_exports_filters_and_audit_frames():
    tracks = {
        1: _track(1, [_det(0, 1, 0, 30), _det(3, 1, 0, 70), _det(6, 1, 0, 50)]),
        2: _track(2, [_det(3, 2, 1, 80)]),                     # spurious single
        3: _track(3, [_det(0, 3, 2, 12), _det(3, 3, 2, 20), _det(6, 3, 2, 18)]),  # unreadable
    }
    frames = {0: tracks[1]["dets"][:1] + tracks[3]["dets"][:1],
              3: [tracks[1]["dets"][1], tracks[2]["dets"][0], tracks[3]["dets"][1]],
              6: [tracks[1]["dets"][2], tracks[3]["dets"][2]]}

    kept, boxes = track.select_exports(tracks, frames, audit_idxs=[], min_dets=3, min_best_side=60)
    assert set(kept) == {1}
    assert set(boxes) == {3}                                   # track 1's close-up only
    assert [b["track"] for b in boxes[3]] == [1]               # dropped tracks draw nothing

    # An audit frame is exported even when the model found nothing on it -- that
    # is the entire point: signs it never detects never otherwise reach CVAT.
    kept, boxes = track.select_exports(tracks, frames, audit_idxs=[99], min_dets=3, min_best_side=0)
    assert set(kept) == {1, 3}
    assert boxes[99] == []
    assert set(boxes) == {3, 99}                               # both close-ups land on frame 3


def test_build_coco_puts_every_box_on_its_own_image():
    records = [{"images": [
        {"file": "a_f000003.jpg", "frame": 3, "width": 2304, "height": 1296,
         "boxes": [{"track": 1, "cls": 0, "conf": 0.9, "bbox": [10, 20, 70, 70]},
                   {"track": 4, "cls": 2, "conf": 0.5, "bbox": [30, 40, 50, 60]}]},
        {"file": "a_f000009.jpg", "frame": 9, "width": 2304, "height": 1296,
         "boxes": [{"track": 5, "cls": 1, "conf": 0.7, "bbox": [1, 2, 3, 4]}]},
    ]}]
    doc = track.build_coco(records, ["Regulatory", "Warning", "Information"])

    by_id = {i["id"]: i["file_name"] for i in doc["images"]}
    landed = {(by_id[a["image_id"]], a["category_id"], tuple(a["bbox"])) for a in doc["annotations"]}
    assert landed == {
        ("a_f000003.jpg", 1, (10, 20, 70, 70)),
        ("a_f000003.jpg", 3, (30, 40, 50, 60)),
        ("a_f000009.jpg", 2, (1, 2, 3, 4)),
    }
    assert [c["name"] for c in doc["categories"]] == ["Regulatory", "Warning", "Information"]
    assert doc["annotations"][0]["area"] == 70 * 70


def test_pass2_writes_the_frame_pass1_actually_saw(tmp_path):
    """The two passes must agree on what "frame 17" means.

    pass1 counts frames off ``cap.read()``, pass2 off ``cap.grab()``. If those
    ever disagreed, every box would be drawn on a neighbouring frame and nothing
    would look wrong -- so paint the frame number into the pixels and check it.
    """
    video = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 64))
    for n in range(30):
        writer.write(np.full((64, 64, 3), n * 8, np.uint8))
    writer.release()

    images_dir, crops_dir = tmp_path / "images", tmp_path / "crops"
    images_dir.mkdir()
    crops_dir.mkdir()
    wanted = {5: [], 17: []}
    written = track.pass2(video, wanted, {}, "clip", images_dir, crops_dir)

    assert [i["frame"] for i in written] == [5, 17]
    for image in written:
        got = cv2.imread(str(images_dir / image["file"])).mean()
        assert abs(got - image["frame"] * 8) < 12, f"frame {image['frame']} decoded as {got:.0f}"


def test_fingerprint_guard_catches_a_frame_offset(tmp_path):
    """pass1 derives frame numbers from ultralytics' stride arithmetic -- an internal
    that can change under us. If it ever drifts, the guard has to stop the run rather
    than write a dataset whose every box sits two frames late."""
    video = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 64))
    for n in range(30):
        writer.write(np.full((64, 64, 3), n * 8, np.uint8))
    writer.release()

    images_dir, crops_dir = tmp_path / "images", tmp_path / "crops"
    images_dir.mkdir()
    crops_dir.mkdir()

    def prints_for(idxs):
        cap, out, i = cv2.VideoCapture(str(video)), {}, 0
        while len(out) < len(idxs) and cap.grab():
            if i in idxs:
                out[i] = track.fingerprint(cap.retrieve()[1])
            i += 1
        cap.release()
        return out

    honest = prints_for({5, 17})
    assert honest == prints_for({5, 17}), "fingerprint must be stable or every run dies"
    assert honest[5] != honest[17], "fingerprint must tell two frames apart to be worth anything"
    assert track.pass2(video, {5: [], 17: []}, {}, "clip", images_dir, crops_dir, honest)

    with pytest.raises(SystemExit, match="every box would land on the wrong picture"):
        track.pass2(video, {5: []}, {}, "clip", images_dir, crops_dir, {5: honest[17]})
