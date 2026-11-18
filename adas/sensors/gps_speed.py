#!/usr/bin/env python3
"""GPS module -> vehicle speed for the ADAS display.

Reads NMEA sentences from a serial GPS (u-blox NEO-6M, e.g. a GY-NEO6MV2
board) and sends {"speed": km/h} over UDP once per fix, like any other speed
source. It needs nothing from the car, so it works on any vehicle.

Only speed for now. The $GPRMC sentence carries it (in knots); while the module
has no lock nothing is sent, so the display shows "--" after its 3 s timeout
instead of a made-up number.

Wiring (Pi 40-pin header, physical pins):
    VCC -> pin 4 (5V)     GND -> pin 14 (or any GND)
    TX  -> pin 10 (GPIO 15, RXD)     RX -> pin 8 (GPIO 14, TXD)
TX and RX cross over. Needs dtparam=uart0=on in /boot/firmware/config.txt and
no serial console on that port. On a Pi 5 those header pins are /dev/ttyAMA0;
/dev/serial0 points at the separate debug connector instead.

    python3 adas/sensors/gps_speed.py
    python3 adas/sensors/gps_speed.py --device /dev/ttyAMA0 --baud 9600 --verbose

Sends to 127.0.0.1:9100 by default, or to every target in ADAS_UDP_TARGETS.
Logs only when the state changes (no data, waiting for a lock, locked), so a
long drive doesn't fill the journal on the SD card.
"""
from __future__ import annotations

import argparse
import os
import select
import signal
from typing import Optional

KNOTS_TO_KMH = 1.852
# Standing still, a GPS still reports a drifting 0.5-2 km/h; below this it's 0.
MIN_SPEED_KMH = 3.0
NO_DATA_S = 3.0      # silence on the serial port for this long = wiring problem


def nmea_checksum_ok(line: str) -> bool:
    """True if the line is "$...*hh" and hh matches the XOR of the body."""
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, given = line[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(given[:2], 16)
    except ValueError:
        return False


def rmc_speed_kmh(line: str) -> Optional[float]:
    """Speed in km/h from a valid RMC sentence, else None.

    None means: not an RMC sentence, corrupt, or the module has no lock yet.
    Any talker is accepted ($GPRMC, $GNRMC, ...), as later modules use GN.
    """
    line = line.strip()
    if not nmea_checksum_ok(line):
        return None
    fields = line[1:].split("*")[0].split(",")
    if len(fields) < 8 or not fields[0].endswith("RMC"):
        return None
    if fields[2] != "A":                       # A = valid, V = no lock
        return None
    if len(fields) > 12 and fields[12][:1] == "N":   # NMEA 2.3 mode: N = not valid
        return None
    try:
        knots = float(fields[7])
    except ValueError:
        return None
    return knots * KNOTS_TO_KMH


def shown_speed(kmh: float, min_speed: float = MIN_SPEED_KMH) -> float:
    """What the display should show: standing-still drift reads as 0."""
    return 0.0 if kmh < min_speed else round(kmh, 1)


def open_serial(device: str, baud: int) -> int:
    """Open the port raw at `baud` (no pyserial needed; Linux only)."""
    import termios
    import tty

    fd = os.open(device, os.O_RDONLY | os.O_NOCTTY)
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    rate = getattr(termios, f"B{baud}")
    attrs[2] |= termios.CLOCAL | termios.CREAD
    attrs[4] = attrs[5] = rate
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIFLUSH)      # drop bytes from before the speed was set
    return fd


class StateLog:
    """Print a line only when the reader's state changes."""

    def __init__(self) -> None:
        self.state = ""

    def __call__(self, state: str, text: str) -> None:
        if state != self.state:
            self.state = state
            print(text, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="GPS module -> ADAS speed")
    ap.add_argument("--device", default="/dev/ttyAMA0", help="serial port the GPS TX is on")
    ap.add_argument("--baud", type=int, default=9600, help="NEO-6M default is 9600")
    ap.add_argument("--min-speed", type=float, default=MIN_SPEED_KMH,
                    help="km/h below which the car counts as stopped")
    ap.add_argument("--port", type=int, help="send to 127.0.0.1:PORT only")
    ap.add_argument("--verbose", action="store_true", help="print every speed sent")
    args = ap.parse_args()

    from adas_protocol import SPEED, UdpPublisher

    pub = UdpPublisher(port=args.port) if args.port else UdpPublisher()
    fd = open_serial(args.device, args.baud)
    log = StateLog()

    def stop(*_) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)        # systemd stop -> clean exit
    print(f"gps {args.device} @ {args.baud} -> {pub.targets}", flush=True)

    buf = b""
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], NO_DATA_S)
            if not ready:
                log("silent", f"no data from {args.device}: check wiring (GPS TX -> pin 10) and power")
                continue
            chunk = os.read(fd, 512)
            if not chunk:
                continue
            buf += chunk
            *lines, buf = buf.split(b"\n")
            if len(buf) > 1024:                # never a newline: wrong baud or noise
                buf = b""
            for raw in lines:
                line = raw.decode("ascii", errors="replace").strip()
                if not line[3:6] == "RMC":
                    continue
                kmh = rmc_speed_kmh(line)
                if kmh is None:
                    log("nolock", "receiving, waiting for a satellite lock")
                    continue
                speed = shown_speed(kmh, args.min_speed)
                pub.send({SPEED: speed})
                log("lock", "locked, sending speed")
                if args.verbose:
                    print(f"{speed:.1f} km/h", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
        pub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
