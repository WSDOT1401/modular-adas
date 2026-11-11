# adas-protocol — the message contract

Single source of truth for how on-Pi producers (vehicle sensors, ADAS modules)
talk to whatever displays their output. It belongs to no particular car: a
vehicle integration (today, [w124](https://github.com/WSDOT1401/w124)) publishes vehicle data onto it and reads
ADAS results from it. Define a key once here; import it everywhere. The whole
point is to stop each producer hand-rolling its own socket and re-typing key
strings (where one typo = silently dropped data).

## The vehicle-state channel — `udp://127.0.0.1:9100`

UTF-8 JSON datagrams, `snake_case` keys, all fields optional (partial updates
are fine). Consumers: the ADAS display ([`adas/display`](../display/), parses
them in `AdasState::applyJson()`) and a vehicle's own cluster (the W124 one
reads the vehicle keys in `VehicleState::applyJson()`).

| JSON key | Type | Unit / values | Sent by | Read by |
|---|---|---|---|---|
| `speed` | number | km/h | any speed source | display, W124 cluster |
| `odo` | number | km | speed sensor | W124 cluster |
| `trip` | number | km (wraps at 1000) | speed sensor | W124 cluster |
| `oil_temp` | number | °C | sensors | W124 cluster |
| `outside_temp` | number | °C | sensors | W124 cluster |
| `voltage` | number | V | sensors | W124 cluster |
| `lane_warning` | boolean | departure detected | vision | display |
| `lane_direction` | string | `left`/`right`/`none` | vision | display |
| `lane_confidence` | number | 0..1 | vision | (liveness only) |
| `fcw_warning` | boolean | collision risk ahead | vision | display |
| `fcw_ttc` | number | s to collision, 0 = unknown | vision | display |
| `speed_limit` | number | km/h, 0 = unknown | vision (signs) | display |
| `sign_seen` | string | sign class id, e.g. `speed_limit_60`, `stop` | vision (signs) | display |
| `module_status` | object | `{"lane"/"fcw"/"signs": "on"/"paused"/"off"}` | vision, every cycle | display |
| `system_fault` | string | `""` or a fault id, e.g. `camera_blocked` | vision | display |
| `input` | string | `rotate_cw`/`rotate_ccw`/`press`/`long_press` (one per event) | rotary encoder, buttons | display |

> ⚠️ **Unknown keys are silently dropped** by every consumer. Import the
> constants from `adas_protocol` instead of typing key strings. Translate
> snake_case ⇄ camelCase only at a consumer's `applyJson()` boundary.

**ADAS heartbeat.** The display counts the ADAS as running only while ADAS
keys keep arriving (3 s timeout), so the vision service should send
`module_status` every cycle even when nothing is wrong.

**More than one receiver.** A UDP port has one receiver. When two consumers
run on one Pi (e.g. the W124 cluster on 9100 and the display on 9101), set
`ADAS_UDP_TARGETS=127.0.0.1:9100,127.0.0.1:9101` for the producers;
`UdpPublisher` then sends every datagram to each target.

The machine-readable spec is [`schema/vehicle_state.schema.json`](schema/vehicle_state.schema.json)
(`additionalProperties: false`, so validating a producer's payload against it
catches misspelled keys before they vanish on the wire).

## Other localhost channels (not this library)

CarPlay uses its own TCP channels, not the UDP vehicle-state contract:

| Port | Proto | Purpose |
|------|-------|---------|
| 9100 | UDP | vehicle state (this contract) |
| 9001 | TCP | CarPlay H.264 video |
| 9002 | TCP | CarPlay touch events |
| 9003 | TCP | CarPlay status (also mirrored to `carplay_status.json`) |

## Python usage

```bash
pip install -e adas/protocol/python      # from the repo root
```

```python
from adas_protocol import UdpPublisher, SPEED, ODO, LANE_WARNING, LANE_DIRECTION

with UdpPublisher() as pub:               # defaults to 127.0.0.1:9100
    pub.send({SPEED: 82.0, ODO: 12345.6})
    pub.send({LANE_WARNING: True, LANE_DIRECTION: "left"})
```

## Adding a key

1. Add the constant to [`keys.py`](python/adas_protocol/keys.py) and its entry to
   the [schema](schema/vehicle_state.schema.json);
   `tests/test_protocol.py` fails until both agree.
2. Parse it in the consumer that needs it (for the display,
   `AdasState::applyJson()` in `adas/display/src/AdasState.cpp`).

Keep the spellings identical to this schema.

## Test

```bash
pip install -e adas/protocol/python pytest
python -m pytest adas/protocol/tests
```
