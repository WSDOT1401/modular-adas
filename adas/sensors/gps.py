#!/usr/bin/env python3
"""GPS: the car's speed for the ADAS display, and its fix for the stats screen.

The module sits on the Pi's UART0 (GPIO 14 and 15, physical pins 8 and 10;
its TX to the Pi's RX on GPIO 15) and sends NMEA at 9600 baud, once a second.
Of each second's sentences:

  RMC  fix or none, and the speed over ground in knots
  GGA  satellites used, and HDOP (how well spread they are: under 2 is good)
  GSA  2D or 3D fix
  GSV  satellites in view

While RMC has a fix, its speed goes to the display as ``speed`` (km/h), like
any speed source. Without one nothing is sent, so the display's own staleness
shows "--" after 3 s, never a made-up 0. GPS speed comes from the Doppler
shift: close to the true ground speed when moving, but standing still it
wanders by a km/h or two, so under ``--still`` km/h it reads 0.

Its health goes to the display with it, once a second, as ``gps`` (the
display's GPS icon): ``ok`` with each speed; ``no_fix`` while the module talks
but has no lock; ``no_data`` after 3 s without a good RMC (a wire off, no
power, the port missing). If this script itself stops, the display notices
the silence and shows the GPS as not working too.

Once a second the fix also goes to /dev/shm/adas-gps.json (RAM, not the SD
card) for the stats screen (adas/vision/tools/stats_window.py, its header).

The port is /dev/ttyAMA0, not /dev/serial0: on a Pi 5 serial0 is the debug
UART (ttyAMA10). /boot/firmware/config.txt needs ``dtparam=uart0=on`` and
cmdline.txt no serial console on it; the user needs the dialout group.

    python3 adas/sensors/gps.py                 # run (the service does this)
    python3 adas/sensors/gps.py --selfcheck     # sample sentences, no GPS needed

At boot, a user service like the rotary encoder's:

    cp adas/sensors/adas-gps.service ~/.config/systemd/user/
    systemctl --user daemon-reload && systemctl --user enable --now adas-gps
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

GPS_FILE = Path("/dev/shm/adas-gps.json")       # adas/vision/tools/stats_window.py reads it
KNOT_KMH = 1.852
MODES = {"1": "no", "2": "2D", "3": "3D"}       # GSA's fix mode
NO_DATA_S = 3.0                                 # no good RMC this long: the module is lost


def valid(line: str) -> bool:
    """A whole sentence whose checksum (XOR of everything between $ and *) matches."""
    body, star, cs = line[1:].partition("*")
    if not line.startswith("$") or not star:
        return False
    x = 0
    for ch in body:
        x ^= ord(ch)
    try:
        return x == int(cs[:2], 16)
    except ValueError:
        return False


def parse(line: str, fix: dict) -> bool:
    """Fold one sentence into ``fix``. True on RMC, the one with the speed: the
    moment to publish. The other three come later in the same second, so
    what they add is at most a second old by the next RMC."""
    if not valid(line):
        return False
    f = line[1:].partition("*")[0].split(",")
    kind = f[0][2:]                                 # GPRMC, GNRMC, ... -> RMC
    try:
        if kind == "RMC" and len(f) > 7:
            fix["fix"] = f[2] == "A"
            fix["speed_kmh"] = float(f[7]) * KNOT_KMH if fix["fix"] and f[7] else None
            return True
        if kind == "GGA" and len(f) > 8:
            fix["sats_used"] = int(f[7] or 0)
            fix["hdop"] = float(f[8]) if f[8] else None
        elif kind == "GSA" and len(f) > 2:
            fix["mode"] = MODES.get(f[2], "no")
        elif kind == "GSV" and len(f) > 3:
            fix["sats_in_view"] = int(f[3] or 0)
    except ValueError:
        pass                                        # a garbled field: keep the last good values
    return False


def speed(fix: dict, still: float) -> Optional[float]:
    """km/h for the display, or None: no fix, so nothing to send."""
    v = fix.get("speed_kmh")
    if not fix.get("fix") or v is None:
        return None
    return 0.0 if v < still else round(v, 1)


def write(fix: Optional[dict]) -> None:
    """Replace GPS_FILE in one step (a reader never sees half a file); None
    removes it: the module has gone quiet."""
    try:
        if fix is None:
            GPS_FILE.unlink(missing_ok=True)
            return
        tmp = GPS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(fix))
        os.replace(tmp, GPS_FILE)
    except OSError:
        pass                                        # no /dev/shm (not Linux)


def main() -> int:
    ap = argparse.ArgumentParser(description="GPS speed to the ADAS display, the fix to the stats screen")
    ap.add_argument("--port", default="/dev/ttyAMA0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--still", type=float, default=2.0,
                    help="km/h under which the car counts as stopped (default 2)")
    ap.add_argument("--selfcheck", action="store_true", help="check the parsing and quit")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return 0

    import time

    import serial  # type: ignore    # pyserial (python3-serial on the Pi)
    from adas_protocol import GPS, SPEED, UdpPublisher

    pub = UdpPublisher()
    try:
        port = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        # No such port (UART switched off, wrong name): tell the display, and
        # let the service restart us.
        pub.send({GPS: "no_data"})
        print(f"cannot open {args.port}: {e}", flush=True)
        time.sleep(2)
        return 1

    fix: dict = {}
    last_rmc = time.monotonic()                     # the last good RMC
    last_lost = 0.0                                 # the last "no_data" sent
    with port:
        while True:
            raw = port.readline()                   # a line, or what came in 1 s
            now = time.monotonic()
            if raw and parse(raw.decode("ascii", "replace").strip(), fix):
                last_rmc = now
                kmh = speed(fix, args.still)
                pub.send({SPEED: kmh, GPS: "ok"} if kmh is not None else {GPS: "no_fix"})
                write(fix)
            elif now - last_rmc > NO_DATA_S and now - last_lost >= 1.0:
                # No good RMC for 3 s: silence (TX wire off, no power) or only
                # garbage (GND off, wrong baud). Said once a second, like "ok".
                last_lost = now
                fix.clear()
                write(None)
                pub.send({GPS: "no_data"})


def _sentence(body: str) -> str:
    x = 0
    for ch in body:
        x ^= ord(ch)
    return f"${body}*{x:02X}"


def _selfcheck() -> None:
    # This car's module indoors on 2026-11-18: no fix yet, 13 satellites in view.
    real = ["$GPRMC,082401.00,V,,,,,,,181126,,,N*7F",
            "$GPGGA,082401.00,,,,,0,00,99.99,,,,,,*69",
            "$GPGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99*30",
            "$GPGSV,4,1,13,01,31,155,,02,44,126,,03,06,182,,04,52,195,*7B"]
    fix: dict = {}
    assert [parse(s, fix) for s in real] == [True, False, False, False]
    assert fix == {"fix": False, "speed_kmh": None, "sats_used": 0, "hdop": 99.99,
                   "mode": "no", "sats_in_view": 13}, fix
    assert speed(fix, 2.0) is None, "no fix: send nothing, so the display shows --"
    assert not parse(real[0].replace(",V,", ",A,"), fix) and not fix["fix"], \
        "a sentence changed in transit must fail its checksum"

    moving = _sentence("GPRMC,082402.00,A,1345.12345,N,10030.54321,E,25.50,54.7,181126,,,A")
    assert parse(moving, fix) and speed(fix, 2.0) == 47.2, fix      # 25.5 knots
    stopped = _sentence("GPRMC,082403.00,A,1345.12345,N,10030.54321,E,0.60,,181126,,,A")
    assert parse(stopped, fix) and speed(fix, 2.0) == 0.0, "standing still must read 0"
    garbled = _sentence("GPRMC,082404.00,A,,,,,x.y,,181126,,,A")
    assert not parse(garbled, fix) and speed(fix, 2.0) == 0.0, "a bad number keeps the last speed"
    print("ok: checksums; no fix -> nothing sent; fix -> km/h; standing still -> 0")


if __name__ == "__main__":
    raise SystemExit(main())
