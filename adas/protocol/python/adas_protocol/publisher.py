"""UDP publisher for the vehicle-state contract.

Every on-Pi data source (speed sensor, IMU, vision modules, rotary encoder,
...) pushes UTF-8 JSON datagrams through this one class, so the socket setup
and the wire format live in exactly one place.

Where it sends, in order of precedence:

1. ``targets=[("127.0.0.1", 9100), ...]`` passed in code;
2. ``host=`` / ``port=`` passed in code (one target);
3. the ``ADAS_UDP_TARGETS`` environment variable, e.g.
   ``127.0.0.1:9100,127.0.0.1:9101`` — for when two displays listen (each
   UDP port has exactly one receiver);
4. ``127.0.0.1:9100``.

Why UDP and not a file: commit 4135abb replaced state.json polling with UDP
push to spare the Pi's SD card from write wear. Producers must push, not write.
"""
from __future__ import annotations

import json
import os
import socket
from typing import Iterable, List, Optional, Tuple

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9100
TARGETS_ENV = "ADAS_UDP_TARGETS"

Target = Tuple[str, int]


def parse_targets(spec: str) -> List[Target]:
    """Parse ``"host:port,host:port"`` into a list of (host, port)."""
    targets: List[Target] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        host, sep, port = item.rpartition(":")
        if not sep or not host or not port.isdigit():
            raise ValueError(f"{TARGETS_ENV}: expected host:port, got {item!r}")
        targets.append((host, int(port)))
    if not targets:
        raise ValueError(f"{TARGETS_ENV} is set but names no target")
    return targets


class UdpPublisher:
    """Fire-and-forget JSON-over-UDP sender.

    Example::

        from adas_protocol import UdpPublisher, SPEED, ODO
        with UdpPublisher() as pub:
            pub.send({SPEED: 82.0, ODO: 12345.6})
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        targets: Optional[Iterable[Target]] = None,
    ) -> None:
        if targets is not None:
            self._targets = [(h, int(p)) for h, p in targets]
        elif host is not None or port is not None:
            self._targets = [(host or DEFAULT_HOST, int(port or DEFAULT_PORT))]
        elif os.environ.get(TARGETS_ENV):
            self._targets = parse_targets(os.environ[TARGETS_ENV])
        else:
            self._targets = [(DEFAULT_HOST, DEFAULT_PORT)]
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    @property
    def targets(self) -> List[Target]:
        return list(self._targets)

    def send(self, payload: dict) -> None:
        """Encode ``payload`` as compact UTF-8 JSON and push one datagram to
        every target.

        Keys should come from ``adas_protocol.keys``; consumers silently drop
        unrecognized keys, so this intentionally does not validate them
        (validate against schema/vehicle_state.schema.json in tests to catch
        typos early).
        """
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        for addr in self._targets:
            self._sock.sendto(data, addr)

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "UdpPublisher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
