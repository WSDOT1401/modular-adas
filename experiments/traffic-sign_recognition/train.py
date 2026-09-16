"""Train one YOLO26n run on a prepared GTSDB dataset, then export it for the Pi.

One run = one (label_set, imgsz) pair. Produces the usual ultralytics output
(``weights/best.pt``, ``results.csv``, ``results.png``, ``confusion_matrix.png``)
plus ``run_meta.json`` holding the headline metrics, wall time, resolved
optimizer and a sha256 of the weights, so ``report.py`` never has to re-run
anything.

Usage::

    python3 train.py --data datasets/gtsdb-4class/data.yaml --label-set 4class --imgsz 640
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import time

import classes

HERE = pathlib.Path(__file__).resolve().parent

DEFAULT_WEIGHTS = "yolo26n.pt"
EPOCHS = 100
BATCH = 16
PATIENCE = 30

# NCNN precisions to export. Both feed the NCNN / NCNN-FP16 rows in
# experiments/object_detection/benchmark_yolo.py.
NCNN_VARIANTS = {"fp32": {}, "fp16": {"half": True}}


def ncnn_dir_name(tag: str) -> str:
    """Export directory name for one precision.

    The ``_ncnn_model`` suffix is mandatory, not cosmetic: ultralytics infers a
    model's format by substring-matching the filename
    (``AutoBackend._model_type``), so ``best_ncnn_fp32`` loads as *no* known
    format and predict() dies with "not a supported model format". The precision
    tag therefore goes in the middle.
    """
    return f"best_{tag}_ncnn_model"


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _export_ncnn(best: pathlib.Path, imgsz: int) -> dict[str, str]:
    """Export ``best.pt`` to NCNN at each precision.

    Every ncnn export lands in ``<stem>_ncnn_model/`` regardless of precision, so
    the second would silently overwrite the first — rename after each. NCNN
    param/bin are architecture-portable, so exporting on Kaggle x86 and running
    on the Pi's ARM is fine.
    """
    from ultralytics import YOLO

    exported: dict[str, str] = {}
    for tag, kwargs in NCNN_VARIANTS.items():
        # fresh model per export: `half` mutates the loaded weights in place
        produced = pathlib.Path(YOLO(str(best)).export(format="ncnn", imgsz=imgsz, **kwargs))
        dest = best.parent / ncnn_dir_name(tag)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(produced), str(dest))
        exported[tag] = str(dest)
    return exported


def train_one(
    data_yaml: pathlib.Path,
    label_set: str,
    imgsz: int,
    *,
    epochs: int = EPOCHS,
    weights: str = DEFAULT_WEIGHTS,
    project: pathlib.Path | None = None,
    export: bool = True,
    device: str | None = None,
    batch: int = BATCH,
    cache: bool = True,
) -> dict:
    """Train, validate the best checkpoint, export, and return a summary dict."""
    from ultralytics import YOLO

    names, _ = classes.label_set(label_set)
    # Carried forward so the report can describe the split honestly.
    meta_path = pathlib.Path(data_yaml).parent / "dataset_meta.json"
    dataset_meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    project = pathlib.Path(project or HERE / "runs" / "detect")
    run_name = f"{label_set}-{imgsz}"

    model = YOLO(weights)
    started = time.perf_counter()
    model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        cache=cache,           # GTSDB's 900 images at 1360x800 fit in RAM. Bigger
                               # frames (Thai dashcam is 2304x1296) do not — pass
                               # cache=False there or Colab OOMs mid-run.
        patience=PATIENCE,
        plots=True,
        seed=0,                # the deliverable is a 640-vs-1024 comparison,
        deterministic=True,    # so run-to-run noise has to be pinned down
        fliplr=0.0,            # mirroring a sign inverts its meaning: a flipped
                               # "turn right" IS "turn left". Default is 0.5.
        optimizer="auto",      # resolves to AdamW here, lr0 = 0.002*5/(4+nc);
                               # report.py records the value it actually chose
        project=str(project),
        name=run_name,
        exist_ok=True,
        **({"device": device} if device else {}),   # Kaggle auto-picks cuda
    )
    wall_seconds = time.perf_counter() - started

    trainer = model.trainer
    save_dir = pathlib.Path(trainer.save_dir)
    best = pathlib.Path(trainer.best)

    # Metrics from the *best* checkpoint, not the last row of results.csv —
    # that row is the final epoch, which patience may have left behind.
    metrics = YOLO(str(best)).val(
        data=str(data_yaml), imgsz=imgsz, split="val",
        project=str(save_dir), name="val_best", exist_ok=True, plots=True,
        **({"device": device} if device else {}),
    )

    summary = {
        "run": run_name,
        "label_set": label_set,
        "dataset": dataset_meta,
        "names": names,
        "imgsz": imgsz,
        "batch": batch,
        "epochs_requested": epochs,
        "epochs_run": int(getattr(trainer, "epoch", epochs - 1)) + 1,
        "optimizer": type(trainer.optimizer).__name__,
        "wall_seconds": round(wall_seconds, 1),
        "save_dir": str(save_dir),
        "best_pt": str(best),
        "best_pt_sha256": _sha256(best),
        "best_pt_bytes": best.stat().st_size,
        "metrics": {k: round(float(v), 5) for k, v in metrics.results_dict.items()},
        "ncnn": _export_ncnn(best, imgsz) if export else {},
    }
    (save_dir / "run_meta.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, type=pathlib.Path, help="path to data.yaml")
    parser.add_argument("--label-set", required=True, choices=classes.LABEL_SETS)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch", type=int, default=BATCH)
    parser.add_argument("--no-cache", action="store_true",
                        help="stream images from disk instead of caching in RAM")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    parser.add_argument("--project", type=pathlib.Path, default=None)
    parser.add_argument("--no-export", action="store_true", help="skip the NCNN exports")
    parser.add_argument("--device", default=None, help="e.g. cpu / 0 / mps (default: auto)")
    args = parser.parse_args(argv)

    summary = train_one(
        args.data, args.label_set, args.imgsz,
        epochs=args.epochs, weights=args.weights,
        project=args.project, export=not args.no_export, device=args.device,
        batch=args.batch, cache=not args.no_cache,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
