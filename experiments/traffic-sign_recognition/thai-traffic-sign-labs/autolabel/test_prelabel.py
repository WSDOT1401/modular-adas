#!/usr/bin/env python3
"""One end-to-end check: picks -> batch -> crops -> CVAT -> dataset.

    python test_prelabel.py

No framework and no fixtures on purpose. It builds a three-frame batch in a temp
directory with a stub detector, walks the whole chain, and asserts on the YOLO
dataset that comes out the far end.

The thing it really guards is **box coordinates surviving the round trip**. They
go pixels -> normalised -> CVAT -> normalised -> pixels -> normalised again, and
when that breaks it breaks silently: you get a dataset full of boxes in the
wrong place and a model that trains to a plausible-looking bad number.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import shutil
import tempfile
import zipfile

import cv2
import numpy as np

import prelabel

CLIPS = {"clipA": ["clipA_f000100", "clipA_f000200"], "clipB": ["clipB_f000050"]}
W, H = 640, 480
# frame_id -> boxes the "detector" found. clipA_f000200 is deliberately absent:
# a real empty frame, which must still reach CVAT and still reach the dataset.
STUB = {
    "clipA_f000100": [(100.0, 50.0, 180.0, 130.0, "Regulatory"),
                      (300.0, 200.0, 360.0, 260.0, "Warning")],
    "clipB_f000050": [(400.0, 100.0, 470.0, 170.0, "Information")],
}


def ns(**kw):
    return argparse.Namespace(**kw)


def build_workspace(ws: pathlib.Path):
    for clip, frames in CLIPS.items():
        (ws / clip / "full").mkdir(parents=True)
        for fid in frames:
            img = np.full((H, W, 3), 40, np.uint8)
            cv2.rectangle(img, (100, 50), (180, 130), (0, 0, 220), -1)
            cv2.imwrite(str(ws / clip / "full" / f"{fid}.jpg"), img)


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="prelabel-test-"))
    prelabel.BATCHES = tmp / "batches"
    prelabel.DATASET = tmp / "dataset"
    prelabel.BATCHES.mkdir(parents=True)
    ws = tmp / "workspace"
    build_workspace(ws)

    # --- step 1: the human picked these -----------------------------------
    picks = [(c, f, "empty" if f == "clipA_f000200" else "sign")
             for c, fs in CLIPS.items() for f in fs]
    d = prelabel.create("b99", picks, ws)
    assert (d / "manifest.csv").exists()
    assert len(prelabel.rows(d / "manifest.csv")) == 3
    assert prelabel.stage_of(d) == "picked -> detect"

    # --- step 2: detect. Stub the model by pre-writing its output ----------
    prelabel.write_rows(
        d / "boxes.csv", ["frame_id", "x1", "y1", "x2", "y2", "coarse", "conf"],
        sorted((f, *b[:4], b[4], 0.9) for f, bs in STUB.items() for b in bs))
    meta = json.loads((d / "batch.json").read_text())
    meta["detected"] = sorted(f for fs in CLIPS.values() for f in fs)
    (d / "batch.json").write_text(json.dumps(meta, indent=2) + "\n")

    prelabel.cmd_detect(ns(bid="b99", model=None, imgsz=1280, conf=0.25))
    smap = prelabel.rows(d / "source_map.csv")
    assert len(smap) == 3, smap
    assert len(list((d / "crops").glob("*.jpg"))) == 3
    # the detector must not have been re-run for the empty frame
    assert json.loads((d / "batch.json").read_text())["detected"] == \
        sorted(f for fs in CLIPS.values() for f in fs)

    # --- step 3: Colab ----------------------------------------------------
    prelabel.cmd_to_colab(ns(bid="b99"))
    assert (d / "crops.zip").exists()
    assert prelabel.stage_of(d) == "waiting on colab"

    pred = tmp / "predictions.csv"
    guess = {"Regulatory": "stop", "Warning": "left_curve", "Information": "u_turn"}
    prelabel.write_rows(pred, ["crop_id", "pred"],
                        [(r["crop_id"], guess[r["coarse"]]) for r in smap])
    prelabel.cmd_from_colab(ns(bid="b99", csv=pred))
    assert len(prelabel.rows(d / "predictions.csv")) == 3

    # a predictions.csv from another batch must be refused, not merged
    other = tmp / "wrong.csv"
    prelabel.write_rows(other, ["crop_id", "pred"], [("someoneelse_f000001_b0", "stop")])
    try:
        prelabel.cmd_from_colab(ns(bid="b99", csv=other))
        raise AssertionError("accepted a predictions.csv from the wrong batch")
    except SystemExit:
        pass

    # --- step 4: CVAT out -------------------------------------------------
    prelabel.cmd_to_cvat(ns(bid="b99"))
    with zipfile.ZipFile(d / "review.zip") as z:
        names = {pathlib.PurePath(n).name: n for n in z.namelist()}
        assert "obj.names" in names
        assert z.read(names["obj.names"]).decode().split() == prelabel.NAMES
        # the empty frame must carry an empty .txt, not no .txt at all
        assert "clipA_f000200.txt" in names
        assert z.read(names["clipA_f000200.txt"]).decode().strip() == ""
        a_txt = z.read(names["clipA_f000100.txt"]).decode().splitlines()
        assert len(a_txt) == 2, a_txt
        # stop is class 0; check the geometry round-tripped to normalised xywh
        cls, cx, cy, bw, bh = a_txt[0].split()
        assert int(cls) == prelabel.IDX["stop"]
        assert abs(float(cx) - 140 / W) < 1e-4, cx
        assert abs(float(bw) - 80 / W) < 1e-4, bw

    # --- the group reviews: accept one, relabel one, delete one, add one ---
    review = tmp / "reviewed.zip"
    stage = tmp / "_cvat"
    stage.mkdir()
    shutil.copy(d / "review.zip", tmp / "_in.zip")
    with zipfile.ZipFile(tmp / "_in.zip") as z:
        z.extractall(stage)
    data = stage / "obj_train_data"
    lines = (data / "clipA_f000100.txt").read_text().splitlines()
    # box 0 untouched (accepted); box 1 relabelled left_curve -> pedestrian_crossing
    parts = lines[1].split()
    parts[0] = str(prelabel.IDX["pedestrian_crossing"])
    (data / "clipA_f000100.txt").write_text(lines[0] + "\n" + " ".join(parts) + "\n")
    # clipB: the one box deleted, a different one drawn by hand
    (data / "clipB_f000050.txt").write_text(
        f"{prelabel.IDX['information']} 0.200000 0.300000 0.100000 0.100000\n")
    shutil.make_archive(str(review.with_suffix("")), "zip", stage)

    prelabel.cmd_from_cvat(ns(bid="b99", zip=review, iou=0.5))
    rev = prelabel.rows(d / "reviewed.csv")
    assert len(rev) == 3, rev
    assert prelabel.stage_of(d) == "reviewed -> build"
    labs = sorted(r["label"] for r in rev)
    assert labs == ["information", "pedestrian_crossing", "stop"], labs
    # the accepted box must come back at the pixels it went out at
    kept = next(r for r in rev if r["label"] == "stop")
    assert abs(float(kept["x1"]) - 100) < 0.5, kept
    assert abs(float(kept["y2"]) - 130) < 0.5, kept

    # --- step 5: build ----------------------------------------------------
    prelabel.cmd_build(ns(only=None, seed=0))
    ds = prelabel.DATASET
    imgs = list((ds / "images").rglob("*.jpg"))
    assert len(imgs) == 3, imgs
    # the empty frame is in, carrying an empty label file -- that is how YOLO
    # encodes background, and it is the whole point of picking empty frames
    empty = next(p for p in (ds / "labels").rglob("clipA_f000200.txt"))
    assert empty.read_text().strip() == ""
    # clips, not frames, decide the split: no clip may appear on both sides
    sides = {}
    for p in imgs:
        sides.setdefault(p.stem.split("_f")[0], set()).add(p.parent.name)
    assert all(len(v) == 1 for v in sides.values()), sides
    yaml = (ds / "data.yaml").read_text()
    assert f"nc: {len(prelabel.classes.THAI_FINE_NAMES)}" in yaml

    # --- an unnamed sign must poison its whole frame ----------------------
    prelabel.write_rows(d / "reviewed.csv",
                        ["frame_id", "x1", "y1", "x2", "y2", "label"],
                        [("clipA_f000100", 100, 50, 180, 130, "stop"),
                         ("clipA_f000100", 300, 200, 360, 260, "dont_know"),
                         ("clipB_f000050", 400, 100, 470, 170, "u_turn")])
    prelabel.cmd_build(ns(only=None, seed=0))
    left = {p.stem for p in (prelabel.DATASET / "images").rglob("*.jpg")}
    assert "clipA_f000100" not in left, "a frame holding an unnamed sign was kept"
    assert "clipA_f000200" in left and "clipB_f000050" in left, left

    shutil.rmtree(tmp)
    print("\nok — picks -> batch -> crops -> CVAT -> dataset, 3 frames, "
          "geometry preserved")


if __name__ == "__main__":
    main()
