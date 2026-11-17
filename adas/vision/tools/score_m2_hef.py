#!/usr/bin/env python3
"""Score a compiled m2.hef on the Pi's AI HAT -- the number that counts.

tools/check_m2_quant.py measures the DFC's emulator on the compile machine.
This runs the same held-out crops through the real chip, and times it: a
multi-context .hef reloads weights on every inference, and the 2.15 ms/crop
in the journal was measured on a different build.

    python3 adas/vision/tools/score_m2_hef.py --model ~/m2_hailo_model_v2

It also prints macro recall over the classes the dash displays. Micro accuracy
flatters this model: not_a_sign is half the val set, so predicting it often is
cheap accuracy. Macro is the honest number.

--val is pack_m2_val.py's npz, copied from the Mac. Pi only (needs HailoRT).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

VISION = Path(__file__).resolve().parents[1]
CENTRAL = VISION.parent / "experiments" / "central"
MIN_N = 5          # same as train_m2.py: below this a per-class % is noise


def score(pred: np.ndarray, labels: np.ndarray, names, displayed, min_n=MIN_N) -> dict:
    """Pure: everything the report prints, so it can be checked without a chip."""
    n = np.array([(labels == i).sum() for i in range(len(names))])
    hit = np.array([((labels == i) & (pred == i)).sum() for i in range(len(names))])
    scored = [i for i in range(len(names)) if n[i] >= min_n]
    shown = [i for i in scored if names[i] in displayed]
    return {
        "micro": float((pred == labels).mean()),
        "macro": float(np.mean([hit[i] / n[i] for i in shown])) if shown else float("nan"),
        "emitted": len(set(pred.tolist())),
        "dead": [f"{names[i]} (0/{n[i]})" for i in scored if hit[i] == 0],
        "per_class": sorted(((names[i], int(hit[i]), int(n[i]), hit[i] / n[i]) for i in scored),
                            key=lambda r: r[3]),
        "n_shown": len(shown),
    }


def report(r: dict, names, ms: float) -> None:
    print(f"\non the chip: {r['micro']:.1%} micro   {r['macro']:.1%} macro over "
          f"{r['n_shown']} displayed classes")
    print(f"  emits {r['emitted']} of {len(names)} classes")
    if r["dead"]:
        print(f"  ZERO on: {', '.join(r['dead'])}")
    print(f"  {ms:.2f} ms/crop  ({1000 / ms:.0f} crops/s)")
    print("\nworst classes (n >= %d):" % MIN_N)
    for name, hit, n, acc in r["per_class"][:12]:
        print(f"  {name:<22} {acc:5.1%}  ({hit}/{n})")


def selfcheck() -> None:
    names, displayed = ["a", "b", "c"], {"a", "b"}
    labels = np.array([0, 0, 1, 1, 2, 2])
    pred = np.array([0, 1, 1, 1, 2, 2])
    r = score(pred, labels, names, displayed, min_n=2)
    assert abs(r["micro"] - 5 / 6) < 1e-9, r["micro"]
    assert abs(r["macro"] - (0.5 + 1.0) / 2) < 1e-9, r["macro"]   # c is not displayed
    assert r["emitted"] == 3 and not r["dead"]
    assert r["per_class"][0][0] == "a"
    print("ok: scoring math checks out")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=str(CENTRAL / "sign_v3" / "m2_hailo_model"),
                    help="folder with m2.hef + m2.json")
    ap.add_argument("--val", default=str(Path.home() / "m2_val_128.npz"))
    ap.add_argument("--warmup", type=int, default=20, help="crops run before the clock starts")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        selfcheck()
        return 0

    d = np.load(args.val)
    crops, labels = d["crops"], d["labels"].astype(int)
    names = [str(s) for s in d["classes"]]

    sys.path.insert(0, str(VISION))
    from signs.hailo10 import HailoCropClassifier   # type: ignore

    clf = HailoCropClassifier(args.model)
    assert list(clf.classes) == names, "m2.json classes != the val set's label order"
    print(f"{args.model}\n{len(crops)} crops, {len(names)} classes")

    clf.classify(list(crops[:args.warmup]))
    t0 = time.monotonic()
    out = clf.classify(list(crops))
    ms = (time.monotonic() - t0) * 1000 / len(crops)
    clf.close()

    index = {n: i for i, n in enumerate(names)}
    pred = np.array([index[n] for n, _ in out])
    report(score(pred, labels, names, clf.displayed), names, ms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
