# services/lane_departure — ADAS lane-departure warning

A separate Pi process: acquire forward-camera frames → detect lane position →
decide on a warning → **push the event over UDP to `127.0.0.1:9100`** (the
shared vehicle-state contract — see [`libs/protocol`](../../libs/protocol)).
Never writes files, to spare the SD card.

## Status

Greenfield. The **decision + publish path is real**; the CV stages
(`capture` / `preprocess` / `detector`) are stubs raising `NotImplementedError`.
You can develop the cluster's alert UI today using the mock writer.

## Layout

```
config.py        all tunables (camera, ROI, thresholds, hysteresis, UDP)
main.py          entry point + arg parsing + run loop
pipeline.py      orchestrates capture -> preprocess -> detect -> decide -> publish
capture.py       FrameSource: Picamera2 | file replay            (TODO)
preprocess.py    ROI mask + edge extraction                      (TODO)
detector.py      edges -> signed lane offset                     (TODO)
departure.py     offset -> warning state + direction (hysteresis)  ← real, tested
tools/           mock_lane_writer.py (works) · calibrate.py · record_clip.py
tests/           test_departure.py (pure logic) · test_detector.py (skipped)
samples/         sample frames/clips for offline dev (media gitignored)
```

The publisher is **not** local — it comes from `w124_protocol`, so the wire
format lives in exactly one place.

## Setup

```bash
pip install -e libs/protocol/python          # from the repo root — the shared contract
pip install -r services/lane_departure/requirements.txt
```

## Run

```bash
cd services/lane_departure
python3 main.py                  # camera (Picamera2) — once capture.py is implemented
python3 main.py --source=file    # replay config.CLIP_PATH

# bench, no camera — drives the cluster's lane-warning UI:
python3 tools/mock_lane_writer.py
```

## Test

```bash
cd services/lane_departure && python3 -m pytest      # runs test_departure.py
```

## The warning contract

Pushes `{"lane_warning": bool, "lane_direction": "left"|"right"|"none",
"lane_confidence": 0..1}`. These keys are **proposed** — the C++ consumer
silently drops them until `VehicleState` adds the matching `Q_PROPERTY`s and
parses them in `applyJson()`, then QML binds them. See
[`libs/protocol/README.md`](../../libs/protocol/README.md).
