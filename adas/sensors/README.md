# sensors/ — vehicle data that doesn't need the car

Producers for the `vehicle_state` keys that any old car can get without
tapping its wiring. Each one pushes through `adas_protocol` like every other
producer.

| Script | Sends | Hardware |
|---|---|---|
| `gps_speed.py` | `speed` (km/h), once per GPS fix | u-blox NEO-6M on the Pi's serial pins |

## GPS speed

Reads the `$GPRMC` sentence (speed in knots, ×1.852 for km/h). While the module
has no lock it sends nothing, and the display shows `--` after 3 s. Below
3 km/h it sends 0, because a GPS standing still drifts by 0.5–2 km/h.

The NEO-6M reports once a second by default, so the speed on the display
steps once a second.

### Wiring (Pi 40-pin header)

| GPS pin | Pi pin |
|---|---|
| VCC | 4 (5V) |
| GND | 14 (or any GND) |
| TX | 10 (GPIO 15, RXD) |
| RX | 8 (GPIO 14, TXD) |

TX and RX cross over. The antenna needs to see the sky; the first lock can
take a few minutes, and the module's LED blinks once a second once it has one.

### Pi setup

```bash
sudo raspi-config nonint do_serial_cons 1    # no login console on the port
sudo raspi-config nonint do_serial_hw 0      # serial port on (dtparam=uart0=on)
sudo reboot
```

On a Pi 5 the header pins are `/dev/ttyAMA0`. `/dev/serial0` points at the
separate debug connector, so don't use it.

### Run

```bash
python3 adas/sensors/gps_speed.py --verbose      # prints every speed sent
```

As a service, next to the display and encoder:

```bash
cp adas/sensors/deploy/adas-gps.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now adas-gps
journalctl --user -u adas-gps -f
```

It logs only when its state changes (no data / waiting for a lock / locked),
so a long drive doesn't fill the journal on the SD card.

### Tests

```bash
python -m pytest adas/sensors/tests
```

## Later

- Position, heading and time from the same sentences.
- 5 Hz updates (a UBX `CFG-RATE` command to the module) for a smoother speed.
