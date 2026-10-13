#!/usr/bin/env python3
"""Every route, against a temp workspace, with no browser and no real video.

    python test_app.py

Guards three things that are easy to break and silent when broken: the flip
semantics (a frame the detector called empty but a human marked as holding a
sign must reach the batch as "sign"), the path-traversal check on clip names,
and batch creation writing the manifest the CLI expects.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile

import cv2
import numpy as np

sys.argv = ["app.py"]          # app.py parses args in main(), but be explicit
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import app as A
import store
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import prelabel


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="app-test-"))
    A.FOOTAGE, A.WORKSPACE, A.NOTEBOOK = tmp / "footage", tmp / "ws", tmp / "notebook.json"
    A.WORKSPACE.mkdir(parents=True)
    A.FOOTAGE.mkdir()
    prelabel.BATCHES = tmp / "batches"
    prelabel.BATCHES.mkdir()

    clip = "clipA"
    out = A.WORKSPACE / clip
    (out / "full").mkdir(parents=True)
    (out / "thumb").mkdir()
    ids = [f"{clip}_f{n:06d}" for n in (30, 60, 90)]
    for fid in ids:
        img = np.full((480, 640, 3), 40, np.uint8)
        cv2.imwrite(str(out / "full" / f"{fid}.jpg"), img)
        cv2.imwrite(str(out / "thumb" / f"{fid}.jpg"), img)
    (out / "frames.json").write_text(json.dumps({
        "video": clip + ".mp4", "interval_s": 2.0,
        "frames": [{"id": f, "n": int(f[-6:]), "t": i * 2.0, "w": 640, "h": 480}
                   for i, f in enumerate(ids)]}))
    (out / "scores.json").write_text(json.dumps({"frames": {
        ids[0]: [{"xyxy": [10, 10, 60, 60], "coarse": "Regulatory", "conf": 0.9}],
        ids[1]: [], ids[2]: []}}))
    (A.FOOTAGE / f"{clip}.mp4").write_bytes(b"")

    c = A.app.test_client()
    assert c.get("/").status_code == 200
    assert c.get(f"/clip/{clip}").status_code == 200
    assert c.get(f"/img/thumb/{clip}/{ids[0]}.jpg").status_code == 200
    assert c.get(f"/img/full/{clip}/{ids[0]}.jpg").status_code == 200
    # a clip name arrives from the URL and must not escape the workspace
    assert c.get("/img/full/..%2f..%2fetc/passwd.jpg").status_code in (400, 404)

    # pick all three, and flip the last: the detector saw no sign, the human did
    r = c.post(f"/clip/{clip}/selection", json={"selected": ids, "flipped": [ids[2]]})
    assert r.status_code == 200 and r.get_json()["saved"] == 3
    assert store.load(A.NOTEBOOK)["clips"][clip]["flipped"] == [ids[2]]
    assert "2 sign / 1 empty" in c.get("/").get_data(as_text=True)

    assert c.post("/batch", data={"bid": "b01", "clip": [clip]}).status_code == 302
    d = next(prelabel.BATCHES.glob("b01-*"))
    man = {x["frame_id"]: x["picked_as"] for x in prelabel.rows(d / "manifest.csv")}
    assert man == {ids[0]: "sign", ids[1]: "empty", ids[2]: "sign"}, man
    assert c.post("/batch", data={"bid": "bad id!", "clip": [clip]}).status_code == 400

    shutil.rmtree(tmp)
    print("ok — routes, flip semantics, traversal guard, batch creation")


if __name__ == "__main__":
    main()
