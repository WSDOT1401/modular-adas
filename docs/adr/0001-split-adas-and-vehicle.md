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
| `experiments/` | `adas/experiments/` |
| `models/` | `adas/models/` |
| `tests/` | `adas/tests/` |
| `environment.yml` | `adas/environment.yml` |
| `.gitattributes` (LFS rule) | `adas/.gitattributes` |
| ADAS rules in `.gitignore` | `adas/.gitignore` |
| `package.json` | `w124/package.json` |

The root keeps only what belongs to the whole repository: `README.md`,
`docs/` (decisions that span both halves, like this one), `.github/`, and a
generic `.gitignore` (OS, editor, build and cache files).

Rules:

- `adas/` never imports from `w124/`, and `w124/` never imports from `adas/`.
  They meet only through the message channel defined in `adas/protocol/`.
- Each folder keeps its own `.gitignore` (and `adas/` its `.gitattributes`)
  and refers only to paths inside itself, so either can be split into its own
  repository without edits.

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
- Scripts and notebooks that take repo-root-relative paths now start with
  `adas/experiments/…` (the Kaggle notebook clones the repo and `cd`s there).
- Merging a branch that still uses the old layout (checked against
  `experiments/traffic-sign_recognition`): git places its new files under
  `adas/experiments/` itself but flags each one as a "file location"
  conflict, resolved with `git add`. The real work is `.gitignore`: rules the
  branch added at the root move to `adas/.gitignore` without the `adas/`
  prefix. Code that spells out `experiments/…` from the repo root (the Colab
  notebooks' `EXP` path) needs the `adas/` prefix.
