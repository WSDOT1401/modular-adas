# 0001 — Split the modular ADAS from the W124 vehicle integration

Status: accepted (step 1 implemented) · 2026-11-08 · updated 2026-11-09:
`w124/` moved to its own repository (see the end)

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

- Anyone with an existing checkout must reinstall the protocol package:
  `pip uninstall w124-protocol && pip install -e adas/protocol/python`.
- The W124 cluster is no longer built or deployed from this repository; see
  the update below.
- Scripts and notebooks that take repo-root-relative paths now start with
  `adas/experiments/…` (the Kaggle notebook clones the repo and `cd`s there).
- Merging a branch that still uses the old layout (checked against
  `experiments/traffic-sign_recognition`): git places its new files under
  `adas/experiments/` itself but flags each one as a "file location"
  conflict, resolved with `git add`. The real work is `.gitignore`: rules the
  branch added at the root move to `adas/.gitignore` without the `adas/`
  prefix. Code that spells out `experiments/…` from the repo root (the Colab
  notebooks' `EXP` path) needs the `adas/` prefix.

## Update 2026-11-09: `w124/` is its own repository

The rules above let `w124/` leave without edits, so it did:
[WSDOT1401/w124](https://github.com/WSDOT1401/w124), with its history kept (files that lived at
`qt_cluster/`, `apps/cluster/`, `services/vss/`, `services/carplay/` and
`deploy/` were rewritten to their current paths there). This repository now
holds only the ADAS; the `w124/` rows in the table above record where those
files went before they left.

- A Pi runs the cluster from a clone of the w124 repository, installed as a
  systemd user service (see its `cluster/README.md`).
- Car-specific changes go to the w124 repository. Changes to the message
  contract go here, in `adas/protocol/`, and the car follows.
- A branch that still edits the old W124 paths here (`apps/cluster/`,
  `services/vss/`, `services/carplay/`, `deploy/`) will hit modify/delete
  conflicts; move those edits to the w124 repository instead.
