"""Contract tests: keys, schema and publisher agree."""
from __future__ import annotations

import json
import pathlib
import socket

import pytest

import adas_protocol as ap

SCHEMA = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "schema" / "vehicle_state.schema.json")
    .read_text(encoding="utf-8")
)


def test_schema_lists_exactly_the_python_keys():
    assert set(SCHEMA["properties"]) == set(ap.ALL_KEYS)


def test_schema_enums_match_python():
    props = SCHEMA["properties"]
    assert tuple(props["lane_direction"]["enum"]) == ap.LANE_DIRECTIONS
    assert tuple(props["input"]["enum"]) == ap.INPUT_EVENTS
    modules = props["module_status"]["properties"]
    assert tuple(modules) == ap.MODULES
    for spec in modules.values():
        assert tuple(spec["enum"]) == ap.MODULE_STATES


def _listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2)
    return sock


def test_publisher_sends_to_every_target():
    a, b = _listener(), _listener()
    try:
        targets = [a.getsockname(), b.getsockname()]
        with ap.UdpPublisher(targets=targets) as pub:
            pub.send({ap.SPEED: 50, ap.MODULE_STATUS: {"lane": "on"}})
        for sock in (a, b):
            assert json.loads(sock.recv(4096)) == {"speed": 50, "module_status": {"lane": "on"}}
    finally:
        a.close()
        b.close()


def test_targets_from_environment(monkeypatch):
    monkeypatch.setenv(ap.TARGETS_ENV, "127.0.0.1:9100, 127.0.0.1:9101")
    with ap.UdpPublisher() as pub:
        assert pub.targets == [("127.0.0.1", 9100), ("127.0.0.1", 9101)]


def test_explicit_port_beats_environment(monkeypatch):
    monkeypatch.setenv(ap.TARGETS_ENV, "127.0.0.1:9101")
    with ap.UdpPublisher(port=9200) as pub:
        assert pub.targets == [("127.0.0.1", 9200)]


def test_default_target(monkeypatch):
    monkeypatch.delenv(ap.TARGETS_ENV, raising=False)
    with ap.UdpPublisher() as pub:
        assert pub.targets == [(ap.DEFAULT_HOST, ap.DEFAULT_PORT)]


@pytest.mark.parametrize("bad", ["localhost", "127.0.0.1:", ":9100", ",", "h:p"])
def test_bad_target_spec_is_rejected(bad):
    with pytest.raises(ValueError):
        ap.parse_targets(bad)
