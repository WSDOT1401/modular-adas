# modular-adas

A modular driver-assistance system (ADAS) for a Raspberry Pi 5, and the first
car it runs in: a 1990s Mercedes W124.

| Folder | What it is |
|---|---|
| [`adas/`](adas/) | The ADAS itself, independent of any car: message protocol, vision service, experiments, model manifests. |
| [`w124/`](w124/) | Everything specific to the W124: instrument-cluster dashboard, speed sensor, CarPlay bridge, deploy scripts. |
| [`docs/`](docs/) | Decisions that span both, e.g. [ADR 0001](docs/adr/0001-split-adas-and-vehicle.md) on why the repo is split this way. |

The two folders share no code. They talk only over a local UDP JSON channel
whose keys are defined in [`adas/protocol/`](adas/protocol/). Start with each
folder's README.
