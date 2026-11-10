# adas/ — the modular ADAS

Vehicle-independent driver-assistance software. It takes camera frames and
vehicle data, and publishes warnings for whatever display a vehicle provides.
The W124 integration that uses it lives in its own repository,
[w124](https://github.com/WSDOT1401/w124).

| Folder | What it is |
|---|---|
| `protocol/` | The message contract: key names, JSON schema and the UDP publisher (`adas_protocol` Python package). Every producer and consumer agrees on this and nothing else. |
| `vision/` | The ADAS vision service: camera capture, scheduler, lane departure, traffic signs (signs and most CV stages are still stubs). |
| `experiments/` | Research and prototypes that feed the modules: object-detection benchmarks, distance estimation, traffic-sign training and the auto-label pipeline. Not run in the car. |
| `models/` | Model-weight manifests (what to fetch and its checksum; the weights themselves are never committed). |
| `tests/` | Cross-module tests (end to end; placeholder). Unit tests sit beside the code they test. |
| `environment.yml` | Conda environment for the experiments (Python + Ultralytics). |
| `.gitignore`, `.gitattributes` | Ignore rules for weights, datasets and footage, and the Git LFS rule for trained results. |

## The rule

Nothing in `adas/` imports from a vehicle folder. A vehicle integration
supplies three things, all through the protocol:

1. a producer that publishes vehicle data (speed, …),
2. a display that shows ADAS output to the driver,
3. a config that chooses which ADAS modules run.

## Planned next step

`vision/` will be split into a module host (`runtime/`) and one folder per
swappable function under `modules/` (lane departure, traffic signs, forward
collision), each chosen by a config line. See
[`../docs/adr/0001-split-adas-and-vehicle.md`](../docs/adr/0001-split-adas-and-vehicle.md).

## Setup

```bash
pip install -e adas/protocol/python      # from the repo root
pip install -r adas/vision/requirements.txt
```

Each experiment has its own `requirements.txt` and README.
