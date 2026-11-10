# adas/display — the ADAS display

A Qt Quick app that shows the modular ADAS's alerts to the driver, on a
**round** screen (designed at 720 × 720) or a **4:3** screen (960 × 720). The
layout scales to the real panel, so smaller round screens and 800 × 600 or
1024 × 768 panels work too. The shape is a setting you can change from the
rotary encoder, so one build fits whatever screen a car has.

It never touches hardware. Everything it shows arrives as UDP JSON following
[`adas/protocol`](../protocol/), from whichever process produces it.

```
vision service ─┐  lane / collision / signs / module status / faults
speed source  ──┼─ UDP JSON ─▶ 127.0.0.1:9100 ─▶ adas_display
rotary encoder ─┘  {"input": "press"}, ...
```

## Inputs

| Comes from | Keys | Notes |
|---|---|---|
| Vision service (`adas/vision`) | `lane_warning`, `lane_direction`, `fcw_warning`, `fcw_ttc`, `speed_limit`, `sign_seen`, `module_status`, `system_fault` | Send `module_status` every cycle: if no ADAS key arrives for 3 s the display shows **ADAS not running** and treats every module as off. |
| Any speed source | `speed` | A gearbox sender, GPS, OBD or IMU-based estimate; whoever has it publishes it. Stale after 3 s, then shown as `--`. |
| Driver controls | `input` = `rotate_cw`, `rotate_ccw`, `press`, `long_press` | The rotary encoder script below, a steering-wheel button, or a test script. |

**Adding a sensor** (an MPU-6050 IMU, say): write a small process that reads it
and publishes with `adas_protocol.UdpPublisher`. If it reports something the
protocol doesn't have yet, add the key to
[`keys.py`](../protocol/python/adas_protocol/keys.py) and the
[schema](../protocol/schema/vehicle_state.schema.json) (the protocol tests
check they agree), parse it in `AdasState::applyJson()`
([`src/AdasState.cpp`](src/AdasState.cpp)), and show it from QML. Keep I2C
(GPIO 2/3) free for it; the encoder defaults stay off those pins.

## What the driver sees

Producers report facts; [`AdasState`](src/AdasState.h) decides which one is
shown. One alert at a time, highest first:

| Level | Colour | Reason | Round | 4:3 |
|---|---|---|---|---|
| Warning | red | vehicle ahead (`fcw`) | whole rim pulses, **BRAKE** replaces the speed | red banner, frame pulses |
| System | grey | ADAS not running, fault (e.g. camera blocked) | dashed rim, dashed lane lines | grey banner |
| Caution | amber | drifting left/right | rim lights on that side | amber banner |
| Caution | amber | over the limit (> limit + 2 km/h) | rim lights above the sign, speed turns amber | amber banner |
| Info | blue | sign just read (shown 8 s) | sign appears beside the limit | blue banner, "Signs seen" |

Timings and the overspeed margin are constants at the top of `AdasState.h`;
words and colours live in [`qml/Theme.qml`](qml/Theme.qml).

## Controls

What each control does is decided in one place, `handleInput()` in
[`qml/Main.qml`](qml/Main.qml). Today:

| Encoder | Keyboard | Driving | In settings |
|---|---|---|---|
| hold (0.8 s) | `M` / `Esc` | open settings | close settings |
| press | `Enter` / `Space` | hide the current caution or info alert until it clears (warnings can't be hidden) | change the highlighted item |
| turn | arrow keys | nothing yet | move the highlight |

Settings: screen shape (round / 4:3) and demo scenarios. They are saved
between runs.

### Wiring the encoder (KY-040 style)

| Encoder | Pi (BCM) |
|---|---|
| CLK / A | GPIO 5 |
| DT / B | GPIO 6 |
| SW | GPIO 13 |
| + / GND | 3V3 / GND |

GPIO 17 is used by the W124 speed sensor. Other pins: `--a`, `--b`, `--button`;
wrong direction: `--reverse`.

## Build and run on the Pi

Needs Qt 6.5 or newer (the same as the W124 cluster). Check with
`apt policy qt6-base-dev`.

```bash
sudo apt install -y cmake build-essential qt6-base-dev qt6-declarative-dev \
  qml6-module-qtquick qml6-module-qtquick-window qml6-module-qtquick-shapes qml6-module-qtcore
pip install -e adas/protocol/python             # from the repo root

cd adas/display
cmake -S . -B build && cmake --build build -j
./build/adas_display                            # full screen, listens on UDP 9100
```

Without a camera or car, either let the display play its own scenarios or drive
it over UDP like the real thing:

```bash
./build/adas_display --scenario cycle           # built-in demo, no UDP
python3 tools/demo_sender.py                    # real UDP path, all scenarios
python3 tools/demo_sender.py --scenario fcw     # hold one
python3 input/rotary_encoder.py                 # the encoder, on the Pi
```

Options: `--shape round|rect` (overrides the saved setting), `--windowed`,
`--port N`, `--scenario NAME|cycle`, `--snapshot out.png` (render, save, quit;
handy for checking a layout change).

Fonts: the design uses [Jost](https://fonts.google.com/specimen/Jost) (free,
Futura-like). Put its `.ttf` files in `assets/fonts/`; without them the
system font is used.

### Start at boot

User services, like the W124 cluster's:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/adas-display.service deploy/adas-encoder.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now adas-display adas-encoder
```

They expect the repo at `~/modular-adas`.

### Next to the W124 cluster

Each UDP port has one receiver, and the W124 cluster already listens on 9100.
Run the display on another port and tell producers to send to both:

```bash
./build/adas_display --port 9101
export ADAS_UDP_TARGETS=127.0.0.1:9100,127.0.0.1:9101   # for every adas_protocol producer
```

The W124 speed reader has its own socket, so it still only reaches 9100; until
it sends to 9101 as well, the display shows `--` for speed.

## Not done yet

- The vision service doesn't send the collision, sign, module-status or fault
  keys yet (those stages are stubs), so on the car the display reads
  **ADAS not running** until it does. Use `tools/demo_sender.py` meanwhile.
- No sound. Collision warnings in particular should chime.
- Turning the encoder while driving does nothing yet.
