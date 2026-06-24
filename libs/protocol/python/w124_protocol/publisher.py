"""UDP publisher for the W124 vehicle-state contract.

Every on-Pi data source (VSS reader, analog sender reader, lane-departure
module, ...) pushes UTF-8 JSON datagrams to udp://127.0.0.1:9100 through this
one class, so the socket setup and the wire format live in exactly one place.

Why UDP and not a file: commit 4135abb replaced state.json polling with UDP
push to spare the Pi's SD card from write wear. Producers must push, not write.
"""
from __future__ import annotations

import json
import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9100


class UdpPublisher:
    """Fire-and-forget JSON-over-UDP sender to the cluster.

    Example::

        from w124_protocol import UdpPublisher, SPEED, ODO
        with UdpPublisher() as pub:
            pub.send({SPEED: 82.0, ODO: 12345.6})
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self._addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, payload: dict) -> None:
        """Encode ``payload`` as compact UTF-8 JSON and push one datagram.

        Keys should come from ``w124_protocol.keys``; the consumer silently
        drops unrecognized keys, so this intentionally does not validate them
        (validate against vehicle_state.schema.json in tests if you want to
        catch typos early).
        """
        self._sock.sendto(json.dumps(payload).encode("utf-8"), self._addr)

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "UdpPublisher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
