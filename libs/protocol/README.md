# w124-protocol — the cluster IPC contract

Single source of truth for how on-Pi producers talk to the cluster UI. Define a
key once here; import it everywhere. The whole point is to stop each producer
hand-rolling its own socket and re-typing key strings (where one typo =
silently dropped data).

## The vehicle-state channel — `udp://127.0.0.1:9100`

UTF-8 JSON datagrams, `snake_case` keys, all fields optional (partial updates
are fine). Parsed by `VehicleState::applyJson()` in the Qt cluster.

| JSON key (snake_case) | Type | Unit / values | Qt property (camelCase) | Status |
|---|---|---|---|---|
| `speed` | number | km/h | `speed` | live |
| `odo` | number | km | `odometer` | live |
| `trip` | number | km (wraps at 1000) | `trip` | live |
| `oil_temp` | number | °C | `oilTemp` | live |
| `outside_temp` | number | °C | `outsideTemp` | live |
| `voltage` | number | V | `voltage` | live |
| `lane_warning` | boolean | departure detected | `laneWarningActive` | **proposed** |
| `lane_direction` | string | `left`/`right`/`none` | `laneWarningDirection` | **proposed** |
| `lane_confidence` | number | 0..1 | `laneConfidence` | **proposed** |

> ⚠️ **Unknown keys are silently dropped.** The `lane_*` keys do nothing until
> `VehicleState` gains the matching `Q_PROPERTY`s *and* parses the keys in
> `applyJson()`. Sending them early is harmless. Translate snake_case ⇄
> camelCase only at the `applyJson()` boundary.

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
pip install -e libs/protocol/python      # from the repo root
```

```python
from w124_protocol import UdpPublisher, SPEED, ODO, LANE_WARNING, LANE_DIRECTION

with UdpPublisher() as pub:               # defaults to 127.0.0.1:9100
    pub.send({SPEED: 82.0, ODO: 12345.6})
    pub.send({LANE_WARNING: True, LANE_DIRECTION: "left"})
```

## Consumer (C++) — adding the ADAS keys

To make the `lane_*` keys live, on the Qt side:
1. add `laneWarningActive` / `laneWarningDirection` / `laneConfidence` `Q_PROPERTY`s to `VehicleState`,
2. parse the three keys in `applyJson()`,
3. bind them in QML to render the alert.

Keep the spellings identical to this schema.
