# 0001 — Split the modular ADAS from the W124 vehicle integration

Status: accepted (step 1 implemented) · 2026-11-08

## Context

The project is a modular ADAS whose first and only car is a Mercedes W124. The
code mixed the two: the W124 dashboard, speed sensor, CarPlay bridge and deploy
scripts sat beside the vehicle-independent vision service and message contract
under `apps/`, `services/`, `libs/` and `deploy/`, and the shared Python
package was named `w124_protocol`. That made it hard to see which parts are
reusable, and the W124 parts may later move to a repository of their own.

## Decision

Two top-level folders that share no code, only a message format:

| Old path | New path |
|---|---|
| `apps/cluster/` | `w124/cluster/` |
| `services/vss/` | `w124/vss/` |
| `services/carplay/` | `w124/carplay/` |
| `deploy/` | `w124/deploy/` |
| `config/` | `w124/config/` |
| `libs/protocol/` (package `w124_protocol`) | `adas/protocol/` (package `adas_protocol`) |
| `services/vision/` | `adas/vision/` |

`experiments/`, `models/`, `docs/` and `tests/` stay at the root.

Rules:

- `adas/` never imports from `w124/`, and `w124/` never imports from `adas/`.
  They meet only through the message channel defined in `adas/protocol/`.
- `w124/` keeps its own `.gitignore` and refers only to paths inside itself,
  so it can be split into its own repository without edits.

## Steps

1. **Restructure** (this change): move and rename, fix every path. No change
   in behaviour.
2. **Module host**: split `adas/vision/` into a runtime and one folder per
   swappable module (`adas/modules/lane_departure/`, `traffic_signs/`, …),
   each selected by a line in the vehicle's config.
3. **Alerts end to end**: protocol v1 (sender, timestamp, more than one
   listener), and the W124 cluster shows ADAS warnings.

## Consequences

- Anyone with an existing checkout must rebuild the cluster from
  `w124/cluster/` and reinstall the protocol package:
  `pip uninstall w124-protocol && pip install -e adas/protocol/python`.
- A Pi running the systemd unit needs the unit re-copied: its `ExecStart`
  path now points at `w124/deploy/start_kiosk.sh`.
- `experiments/` still mentions `services/vision/` in a few comments. It was
  left untouched so the open traffic-sign branch merges cleanly; fix those
  after it lands.
