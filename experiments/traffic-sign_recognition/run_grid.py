"""Run the whole experiment grid: {4class, 1class} x {640, 1024}.

Sequential by design — a single free GPU, and the runs are short (~15 min each
on a T4). A failing run is logged and skipped rather than aborting the grid, so
one bad export doesn't cost you the other three results in a 12 h session.

Usage::

    python3 run_grid.py --datasets datasets
"""
from __future__ import annotations

import argparse
import json
import pathlib
import traceback

import classes
import train

HERE = pathlib.Path(__file__).resolve().parent

DEFAULT_IMGSZ = (640, 1024)


def run_grid(
    datasets: pathlib.Path,
    label_sets: tuple[str, ...],
    sizes: tuple[int, ...],
    *,
    epochs: int = train.EPOCHS,
    weights: str = train.DEFAULT_WEIGHTS,
    project: pathlib.Path | None = None,
    export: bool = True,
    device: str | None = None,
) -> list[dict]:
    project = pathlib.Path(project or HERE / "runs" / "detect")
    results: list[dict] = []

    combos = [(ls, sz) for ls in label_sets for sz in sizes]
    for n, (label_set, imgsz) in enumerate(combos, start=1):
        data_yaml = pathlib.Path(datasets) / f"gtsdb-{label_set}" / "data.yaml"
        header = f"[{n}/{len(combos)}] {label_set} @ {imgsz}"
        if not data_yaml.exists():
            print(f"{header}: SKIP — {data_yaml} missing (run prepare_gtsdb.py first)")
            results.append({"run": f"{label_set}-{imgsz}", "error": f"missing {data_yaml}"})
            continue

        print(f"\n{'=' * 70}\n{header}\n{'=' * 70}")
        try:
            results.append(train.train_one(
                data_yaml, label_set, imgsz,
                epochs=epochs, weights=weights, project=project,
                export=export, device=device,
            ))
        except Exception as exc:                      # keep the remaining runs alive
            print(f"{header}: FAILED — {exc}")
            traceback.print_exc()
            results.append({"run": f"{label_set}-{imgsz}", "error": repr(exc)})

    out = project / "grid_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")

    ok = [r for r in results if "error" not in r]
    print(f"\n{len(ok)}/{len(results)} runs succeeded -> {out}")
    for r in results:
        if "error" in r:
            print(f"  FAILED {r['run']}: {r['error']}")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--datasets", type=pathlib.Path, default=HERE / "datasets",
                        help="dir holding gtsdb-<label_set>/data.yaml")
    parser.add_argument("--label-sets", nargs="+", default=list(classes.LABEL_SETS),
                        choices=classes.LABEL_SETS)
    parser.add_argument("--imgsz", nargs="+", type=int, default=list(DEFAULT_IMGSZ))
    parser.add_argument("--epochs", type=int, default=train.EPOCHS)
    parser.add_argument("--weights", default=train.DEFAULT_WEIGHTS,
                        help="starting checkpoint (downloaded if absent)")
    parser.add_argument("--project", type=pathlib.Path, default=None)
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--device", default=None, help="e.g. cpu / 0 / mps (default: auto)")
    args = parser.parse_args(argv)

    results = run_grid(
        args.datasets, tuple(args.label_sets), tuple(args.imgsz),
        epochs=args.epochs, weights=args.weights,
        project=args.project, export=not args.no_export,
        device=args.device,
    )
    return 0 if any("error" not in r for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
