# modular-adas

A modular driver-assistance system (ADAS) for a Raspberry Pi 5. It is
independent of any car; its first car is a 1990s Mercedes W124, whose
integration lives in its own repository, [w124](https://github.com/WSDOT1401/w124).

| Folder | What it is |
|---|---|
| [`adas/`](adas/) | The ADAS: message protocol, vision service, experiments, model manifests. Start with its README. |
| [`docs/`](docs/) | Design decisions, e.g. [ADR 0001](docs/adr/0001-split-adas-and-vehicle.md) on why the car-specific code lives elsewhere. |

A car connects to the ADAS only over a local UDP JSON channel whose keys are
defined in [`adas/protocol/`](adas/protocol/). The two share no code.
