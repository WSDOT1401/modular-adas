#!/usr/bin/env python3
"""Rotary encoder with push button -> ADAS display control events.

Reads a 5-pin encoder (KY-040 board or bare EC11) on the Pi's GPIO and sends one UDP datagram per
event ({"input": "rotate_cw" | "rotate_ccw" | "press" | "long_press"}), so the
display never touches hardware and the same events can come from a keyboard,
a steering-wheel button or a test script.

What each event does is decided in one place, handleInput() in
adas/display/qml/Main.qml.

Wiring (BCM numbers; change with the flags):
    CLK / A  -> GPIO 5      DT / B -> GPIO 6      SW -> GPIO 13
    +        -> 3V3         GND    -> GND
A bare encoder has no + pin: its middle pin and the button's other leg go to
GND (the pins use the Pi's internal pull-ups). GPIO 17 is taken by the W124 speed sensor; I2C (GPIO 2/3) is left free for an
IMU such as an MPU-6050.

    python3 adas/display/input/rotary_encoder.py
    python3 adas/display/input/rotary_encoder.py --a 5 --b 6 --button 13 --hold 0.8

Needs gpiozero (preinstalled on Raspberry Pi OS) and adas_protocol.
"""
from __future__ import annotations

import argparse
import signal

from adas_protocol import INPUT, UdpPublisher


def main() -> int:
    ap = argparse.ArgumentParser(description="Rotary encoder -> ADAS display events")
    ap.add_argument("--a", type=int, default=5, help="BCM pin for CLK / A")
    ap.add_argument("--b", type=int, default=6, help="BCM pin for DT / B")
    ap.add_argument("--button", type=int, default=13, help="BCM pin for SW (to GND)")
    ap.add_argument("--hold", type=float, default=0.8, help="seconds that count as a long press")
    ap.add_argument("--reverse", action="store_true", help="swap the turn direction")
    ap.add_argument("--port", type=int, help="send to 127.0.0.1:PORT only")
    args = ap.parse_args()

    from gpiozero import Button, RotaryEncoder  # imported late: Pi-only

    pub = UdpPublisher(port=args.port) if args.port else UdpPublisher()

    def send(event: str) -> None:
        pub.send({INPUT: event})

    cw, ccw = ("rotate_ccw", "rotate_cw") if args.reverse else ("rotate_cw", "rotate_ccw")
    encoder = RotaryEncoder(args.a, args.b, max_steps=0)
    encoder.when_rotated_clockwise = lambda: send(cw)
    encoder.when_rotated_counter_clockwise = lambda: send(ccw)

    button = Button(args.button, pull_up=True, bounce_time=0.02, hold_time=args.hold)
    held = {"now": False}

    def on_held() -> None:
        held["now"] = True
        send("long_press")

    def on_released() -> None:
        if not held["now"]:
            send("press")
        held["now"] = False

    button.when_held = on_held
    button.when_released = on_released

    def stop(*_) -> None:
        raise KeyboardInterrupt

    print(f"encoder A={args.a} B={args.b} button={args.button} -> {pub.targets}")
    signal.signal(signal.SIGTERM, stop)  # systemd stop -> clean GPIO release
    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        encoder.close()
        button.close()
        pub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
