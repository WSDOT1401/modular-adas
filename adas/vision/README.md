# adas/vision — ADAS vision service (traffic signs; lane departure to come)

A separate Pi process: acquire forward-camera frames → detect traffic signs (and,
soon, lane position) → decide on a warning → **push the event over UDP to
`127.0.0.1:9100`** (the shared vehicle-state contract — see
[`adas/protocol`](../protocol)). Never writes files, to spare the SD card.

## Status

- **Traffic signs: running.** The two shipping models (b01 detector and the
  speed reader, in [`adas/experiments/central`](../experiments/central/)) find
  Thai signs and read speed limits; the display shows them. Runs on a dashcam
  clip today; the Pi camera backend is still TODO.
- **Lane departure:** the decision + publish path is real and tested; the CV
  stages (`lane.preprocess` / `lane.detector`) are stubs, so `lane` is not in
  `config.STAGES` yet and the display shows it as switched off.
- **Forward collision:** not started; reads "off".

## Layout

```
main.py                  entry point + arg parsing; runs runtime.Scheduler
config.py                all tunables (camera, ROI, thresholds, hysteresis, UDP)
capture/
  base.py                FrameSource abstraction consumed by the scheduler
  picamera2_source.py    Pi CSI camera backend                          (TODO)
  video_replay_source.py OpenCV clip replay, real-time pace (off-Pi dev)
lane/
  preprocess.py          ROI mask + edge extraction                     (TODO)
  detector.py            edges -> signed lane offset (classical/Hough)  (TODO)
  model.py               learned lane-offset model (optional)           (TODO)
  departure.py           offset -> warning state + direction (hysteresis) ← real, tested
signs/
  detector.py            b01 YOLO: frame -> sign boxes + Thai class names
  tracker.py             one event per physical sign, not one per frame
  speed.py               loads the speed reader (classify.py) and its vote
  pipeline.py            detections -> sign_seen / speed_limit keys
  classes.py             which classes are published (not the other_* catch-alls)
runtime/
  scheduler.py           capture -> enabled stages -> publish (+ heartbeat)
  publisher.py           UDP publisher (re-exports adas_protocol)
  vehicle_state_cache.py latest speed/etc. to gate warnings             (TODO)
  health.py              FPS / drops / SoC temp watchdog                (TODO)
tools/
  bench.py               a clip as the camera: vision + speed sim + display, one command
  mock_lane_writer.py    synthetic warnings over UDP (works, no camera)
  calibrate.py           interactive ROI/warp calibration               (TODO)
  record_clip.py         record a clip into tests/fixtures/             (TODO)
tests/
  unit/                  test_departure.py, test_signs.py (pure logic) · test_detector.py (skipped)
  replay/                clip-driven detector tests                     (TODO)
  fixtures/              sample frames/clips for offline dev (media gitignored)
```

The publisher is **not** local — it comes from `adas_protocol`, so the wire
format lives in exactly one place.

## Setup

```bash
pip install -e adas/protocol/python          # from the repo root — the shared contract
pip install -r adas/vision/requirements.txt  # includes torch + ultralytics for signs
```

The weights are not in git (`.pt` is ignored). Copy `b01.pt` and
`speed_reader.pt` into `adas/experiments/central/`, or pass `--weights` and
`--reader`. Without the speed reader, limits are announced with no number.

## Run

```bash
cd adas/vision
python main.py                                        # Pi camera (backend still TODO)
python main.py --source file --clip drive.mp4         # replay a dashcam clip at its own pace
python main.py --source file --clip drive.mp4 --preview   # ...with the boxes drawn in a window
```

Options: `--device mps|0|cpu`, `--every-frame` (don't drop frames to keep
real time), `--loop`, `--stages signs,lane`, `--weights`, `--reader`.

### Bench: a dashcam clip driving the display

One command starts all three and stops them together (q in the preview, or
Ctrl+C):

```bash
cd adas/vision
python tools/bench.py --clip drive.mp4                          # display from adas/display/build
python tools/bench.py --clip drive.mp4 --display path/to/adas_display --shape rect
python tools/bench.py --clip drive.mp4 --display none           # display already running (Pi service)
python tools/bench.py --clip drive.mp4 --speed fixed:45         # or cycle, none
```

Or by hand, three terminals from the repo root:

```bash
adas/display/build/adas_display --windowed            # 1. the display (see adas/display)
python adas/display/tools/speed_sim.py                # 2. simulated speed: town and highway
cd adas/vision && python main.py --source file --clip drive.mp4 --preview   # 3. signs from the clip
```

Signs appear on the display as the clip passes them; a read limit replaces
the one on screen, and OVERSPEED trips whenever the simulated speed is over
it. Each event is also printed: `[  12.4 s] {'sign_seen': 'speed_limit',
'speed_limit': 60}`.

On a PC without a GPU, b01 at 1280 px runs at a few frames a second; the
replay drops frames to stay in real time, as the Pi would. `--every-frame`
shows what the model finds when it sees every frame.

## Test

```bash
cd adas/vision && python3 -m pytest      # departure + sign logic; no models needed
```

## The warning contract

Every datagram carries `module_status` (`signs: "on"`, `lane`/`fcw: "off"`
until those stages run) and `system_fault`: the display's heartbeat. On top:

| Stage | Sends |
|---|---|
| signs | `sign_seen: "<class>"` once per sign; for a speed limit `sign_seen: "speed_limit"` at once, then `speed_limit: 60` when the reader's vote settles |
| lane | `lane_warning`, `lane_direction`, `lane_confidence` |

It also listens on udp 9102 for the driver's menu choices (`feature_enable`
from the display): a switched-off stage is skipped, not just hidden, and
reported as `"off"`. Until the first message, everything built is on.

See [`adas/protocol/README.md`](../protocol/README.md).
