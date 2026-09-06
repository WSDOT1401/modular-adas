# services/vision — ADAS vision service (lane departure; signs to come)

A separate Pi process: acquire forward-camera frames → detect lane position (and,
later, traffic signs) → decide on a warning → **push the event over UDP to
`127.0.0.1:9100`** (the shared vehicle-state contract — see
[`libs/protocol`](../../libs/protocol)). Never writes files, to spare the SD card.

## Status

Greenfield. The lane **decision + publish path is real**; the CV stages
(`capture` / `lane.preprocess` / `lane.detector`) and the whole `signs/` package
are stubs raising `NotImplementedError`. You can develop the cluster's alert UI
today using the mock writer.

## Layout

```
main.py                  entry point + arg parsing; runs runtime.Scheduler
config.py                all tunables (camera, ROI, thresholds, hysteresis, UDP)
capture/
  base.py                FrameSource abstraction consumed by the scheduler
  picamera2_source.py    Pi CSI camera backend                          (TODO)
  video_replay_source.py OpenCV clip-replay backend (off-Pi dev)        (TODO)
lane/
  preprocess.py          ROI mask + edge extraction                     (TODO)
  detector.py            edges -> signed lane offset (classical/Hough)  (TODO)
  model.py               learned lane-offset model (optional)           (TODO)
  departure.py           offset -> warning state + direction (hysteresis) ← real, tested
signs/
  detector.py            traffic-sign detection                         (TODO)
  tracker.py             stabilise detections across frames             (TODO)
  classes.py             class-id -> label mapping                      (TODO)
runtime/
  scheduler.py           orchestrates capture -> lane/signs -> publish
  publisher.py           UDP publisher (re-exports w124_protocol)
  vehicle_state_cache.py latest speed/etc. to gate warnings             (TODO)
  health.py              FPS / drops / SoC temp watchdog                (TODO)
tools/
  mock_lane_writer.py    synthetic warnings over UDP (works, no camera)
  calibrate.py           interactive ROI/warp calibration               (TODO)
  record_clip.py         record a clip into tests/fixtures/             (TODO)
tests/
  unit/                  test_departure.py (pure logic) · test_detector.py (skipped)
  replay/                clip-driven detector tests                     (TODO)
  fixtures/              sample frames/clips for offline dev (media gitignored)
```

The publisher is **not** local — it comes from `w124_protocol`, so the wire
format lives in exactly one place.

## Setup

```bash
pip install -e libs/protocol/python          # from the repo root — the shared contract
pip install -r services/vision/requirements.txt
```

## Run

```bash
cd services/vision
python3 main.py                  # camera (Picamera2) — once the capture backend lands
python3 main.py --source=file    # replay config.CLIP_PATH

# bench, no camera — drives the cluster's lane-warning UI:
python3 tools/mock_lane_writer.py
```

## Test

```bash
cd services/vision && python3 -m pytest      # runs tests/unit/test_departure.py
```

## The warning contract

Pushes `{"lane_warning": bool, "lane_direction": "left"|"right"|"none",
"lane_confidence": 0..1}`. These keys are **proposed** — the C++ consumer
silently drops them until `VehicleState` adds the matching `Q_PROPERTY`s and
parses them in `applyJson()`, then QML binds them. See
[`libs/protocol/README.md`](../../libs/protocol/README.md).
