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

```bash
chmod +x pi/start_qt_kiosk.sh
sudo cp pi/w124-qt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable w124-qt.service
sudo systemctl start w124-qt.service
```

Adjust paths in `pi/w124-qt.service` if your project is not under `/home/pi/Zeiger/qt_cluster`.

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

| Source | Hardware | Interface |
|---|---|---|
| **OBD** (`speedSource: "OBD"`) | ELM327 USB adapter (e.g. OBDLink SX) | USB → `/dev/ttyUSB0` |
| **GPS** (`speedSource: "GPS"`) | USB GPS dongle (u-blox 7/8, e.g. GlobalSat BU-353) | USB → `/dev/ttyUSB1` or `/dev/ttyACM0` |

Avoid Bluetooth ELM327 — pairing reliability in a car is poor.

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
