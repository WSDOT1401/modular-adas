# W124 Qt C++ Prototype

This is the C++/Qt 6 production-track prototype for your W124 circular speedometer.

## Why this exists

- HTML version is great for fast iteration.
- This Qt version is the scalable base for production hardware.

## Features

- C++ state service (`VehicleState`) with properties exposed to QML
- QML gauge renderer for circular displays
- Demo mode by default
- External state mode via `state.json`

## Build (Linux / Raspberry Pi OS)

Install dependencies:

```bash
sudo apt update
sudo apt install -y cmake build-essential qt6-base-dev qt6-declarative-dev
```

Build:

```bash
cd qt_cluster
cmake -S . -B build
cmake --build build -j
```

Run demo mode:

```bash
./build/w124_cluster
```

Run with external state file:

```bash
./build/w124_cluster --state --state-file=./state.json --poll-ms=120
```

## State file format

```json
{
  "speed": 88.5,
  "odo": 87266.4,
  "trip": 12.7
}
```

## Pi service setup (optional)

Run from the repo root (the launcher and unit moved to `deploy/`):

```bash
chmod +x deploy/start_kiosk.sh
sudo cp deploy/systemd/w124-cluster.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable w124-cluster.service
sudo systemctl start w124-cluster.service
```

Adjust paths in `deploy/systemd/w124-cluster.service` if your repo is not under `/home/pi/Zeiger/w124-dash`.

---

## Hardware (Raspberry Pi 5)

### Core

| Component | Recommendation | Notes |
|---|---|---|
| **Pi 5** | 4 GB RAM | 2 GB works but tight with Qt6 + Wayland compositor |
| **Storage** | 32 GB A2 microSD or NVMe via M.2 HAT | NVMe preferred — better vibration/heat/write-cycle tolerance in a car |
| **Active cooler** | Pi 5 Active Cooler (official) | Pi 5 throttles at 80°C; enclosed car environment = mandatory |
| **RTC battery** | CR2032 coin cell + ribbon (onboard connector) | Prevents clock reset on power loss |

### Display

The cluster is a single circular gauge — a round or square display fits best:

| Option | Interface | Size |
|---|---|---|
| Waveshare 4" Round DSI (480×480) | DSI (MIPI) | Best fit — matches the circular dial |
| Waveshare 5" Square HDMI (1080×1080) | HDMI | Easier to source |
| Hyperpixel 4.0 Square | DSI | Good Pi-native option |

DSI is preferred over HDMI for car use — fewer connectors to vibrate loose.

### Speed sources

The W124 predates OBD-II. Speed comes from the gearbox VSS sender or GPS.

| Source | Hardware | Interface |
|---|---|---|
| **VSS** (recommended) | Optocoupler circuit tapped to gearbox sender wire | Pi GPIO pin (BCM17 default) |
| **GPS** | USB GPS dongle (u-blox 7/8, e.g. GlobalSat BU-353) | USB → `/dev/ttyACM0` |

### VSS wiring circuit

The W124 gearbox sender outputs a 12V square wave (reed switch or Hall effect).
This must be stepped down to 3.3V before connecting to Pi GPIO.

```
Gearbox sender wire (12V pulses)
        │
       [1kΩ]
        │
        ├──── PC817 optocoupler pin 1 (anode)
        │
       [GND]  ← car chassis ground

PC817 pin 2 (cathode) → car GND
PC817 pin 4 (collector) → [10kΩ pull-up] → Pi 3.3V
PC817 pin 3 (emitter)  → Pi GND
PC817 pin 4 (collector) → Pi GPIO BCM17
```

Result: idle = HIGH (3.3V), each speed pulse = LOW — safe for Pi GPIO.

**Calibration:** edit `PULSES_PER_KM` in `services/vss/vss_reader.py`.
Default is 8000 (W124 typical). Drive a measured 1 km, count pulses logged,
adjust the constant to match.

### Running the VSS reader

The `deploy/start_kiosk.sh` script launches `services/vss/vss_reader.py`
automatically. To disable during bench testing (run from the repo root):

```bash
VSS_DISABLE=1 ./deploy/start_kiosk.sh
```

For bench testing with simulated speed, run the mock writer separately:

```bash
python3 services/vss/mock_state_writer.py --udp --udp-port=9100
```

### Power

| Component | Spec |
|---|---|
| **DC-DC converter** | 12V → 5V/5A (e.g. Pololu D24V50F5 or Geekworm X1004) |
| **Pi 5 supply** | USB-C PD at 5V/5A (27W) — do not use cheap regulators (SD card corruption risk) |
| **Soft shutdown** | Witty Pi 4 HAT or GPIO script watching ignition signal |

### Wiring

```
Car 12V ──→ DC-DC (5V/5A) ──→ Pi 5 USB-C
                              ├── DSI ribbon ──→ Round display
                              ├── USB ──────────→ ELM327 OBD
                              └── USB ──────────→ GPS dongle
```

### OS / software stack

- **OS**: Raspberry Pi OS Bookworm (64-bit) — Wayland (labwc) is default
- **Qt6**: available in Bookworm repos (`qt6-base-dev qt6-declarative-dev`)
- The systemd service sets `QT_QPA_PLATFORM=wayland`, which is correct for Pi 5 + Bookworm
