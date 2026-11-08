# w124/ — Mercedes W124 vehicle integration

Everything in this repository that is specific to one car: the W124 instrument
cluster and the hardware it is wired to. The vehicle-independent ADAS lives in
[`../adas/`](../adas/).

| Folder | What it is |
|---|---|
| `cluster/` | Qt 6 dashboard (C++ / QML): the circular W124 speedometer, page carousel, settings, CarPlay view. Build and hardware notes are in [`cluster/README.md`](cluster/README.md). |
| `vss/` | Gearbox speed sensor reader (GPIO pulses → speed / odometer / trip) and a mock writer for bench testing. |
| `carplay/` | Node.js bridge for the CarPlay USB dongle (video, touch and status over local TCP). |
| `deploy/` | `start_kiosk.sh` launcher and the systemd unit that runs it at boot. |
| `config/` | Per-vehicle settings (placeholder). |
| `package.json` | Node dependency (`canvas`) for the dashboard's image-generation scripts. |
| `.gitignore` | Qt build/deploy output, runtime IPC files, `node_modules/`. |

## How it connects to the ADAS

Only over the local UDP message channel (`127.0.0.1:9100`, JSON). Nothing in
this folder imports code from `../adas/`, and nothing in `../adas/` imports
code from here; the message keys are defined in
[`../adas/protocol/`](../adas/protocol/). That keeps this folder movable to its
own repository later.

## Run

From this folder:

```bash
cmake -S cluster -B cluster/build && cmake --build cluster/build -j
./deploy/start_kiosk.sh
```
