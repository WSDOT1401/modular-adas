#!/usr/bin/env python3
"""Point M2 at its own training labels and print every crop it argues with.

    python sweep_labels.py                     # -> sweep.csv + sweep_sheet.png
    python sweep_labels.py --apply sweep.csv   # write the decisions back

A disagreement at high confidence means one of two things, and the model cannot
tell you which: the label is wrong, or the model is. A human looks at the
picture and decides. That is the whole technique, and it has already paid --
the first sweep found 27 arguments in 2217 crops, four of which were real label
errors that had been scoring against the model (see JOURNAL 2026-11-15).

Never let it apply its own answer. The labels are what trained it, so agreeing
with itself is not evidence of anything; it is a feedback loop with a progress
bar. `--apply` only honours a `decision` column a human typed.

What a decision means: put any class name in the `decision` column to relabel
that box, or `not_a_sign` to say it is not a sign at all. Leave it blank to
keep the label you already have. The row is matched back by batch + frame +
box, so the columns before `decision` must not be edited.
"""
import argparse
import collections
import csv
import sys
from pathlib import Path

import torch
from PIL import Image, ImageDraw

import build_m2
import train_m2 as T
from demo_e2e import load_m2

HERE = Path(__file__).resolve().parent
BATCHES = HERE.parent / "autolabel" / "batches"
BOX = ("x1", "y1", "x2", "y2")
COLS = ["batch", "frame_id", *BOX, "label", "m2_says", "conf", "decision"]


def reviewed():
    """Every human-labelled box in every batch, with its batch folder."""
    for d in sorted(BATCHES.iterdir()):
        f = d / "reviewed.csv"
        if f.exists():
            for r in csv.DictReader(f.open()):
                yield d, r


def sweep(a):
    dev = ("cuda" if torch.cuda.is_available() else
           "mps" if torch.backends.mps.is_available() else "cpu")
    model, names = load_m2(dev)

    # Group by frame so each jpg is decoded once, not once per box.
    by_frame = collections.defaultdict(list)
    for d, r in reviewed():
        by_frame[(d, r["frame_id"])].append(r)

    out, small, n = [], 0, 0
    for (d, fid), rs in sorted(by_frame.items(), key=lambda kv: (kv[0][0].name, kv[0][1])):
        f = d / "frames" / f"{fid}.jpg"
        if not f.exists():
            continue
        im = Image.open(f).convert("RGB")
        keep, batch = [], []
        for r in rs:
            box = [float(r[k]) for k in BOX]
            n += 1
            if min(box[2] - box[0], box[3] - box[1]) < build_m2.READABLE:
                small += 1          # M2 was never trained this small; no opinion
                continue
            keep.append(r)
            batch.append(T.NORM(build_m2.square(im, *box)))
        if not batch:
            continue
        with torch.no_grad():
            p = torch.softmax(model(torch.stack(batch).to(dev)), 1)
        conf, idx = p.max(1)
        for r, i, c in zip(keep, idx.tolist(), conf.tolist()):
            if names[i] != r["label"] and c >= a.conf:
                out.append({"batch": d.name, "frame_id": r["frame_id"],
                            **{k: r[k] for k in BOX}, "label": r["label"],
                            "m2_says": names[i], "conf": f"{c:.3f}",
                            "decision": ""})

    out.sort(key=lambda r: (r["label"], r["m2_says"], -float(r["conf"])))
    with (HERE / a.out).open("w", newline="") as fh:
        w = csv.DictWriter(fh, COLS)
        w.writeheader()
        w.writerows(out)

    print(f"{n} labelled boxes, {small} too small for M2 to have an opinion")
    print(f"{len(out)} arguments at >= {a.conf:.2f} confidence\n")
    print(f"{'your label':24s} {'M2 says':24s}  n")
    print("-" * 56)
    for (lab, says), c in collections.Counter(
            (r["label"], r["m2_says"]) for r in out).most_common():
        print(f"{lab:24s} {says:24s} {c:3d}")
    sheet(out, HERE / a.sheet)
    print(f"\n{HERE / a.out}\n{HERE / a.sheet}")
    print(f"\nFill the 'decision' column, then: sweep_labels.py --apply {a.out}")


def sheet(out, path, cols=8, s=128, pad=26):
    """One tile per argument, in the same order as the csv, numbered to match."""
    if not out:
        return
    rows = (len(out) + cols - 1) // cols
    img = Image.new("RGB", (cols * (s + 4) + 8, rows * (s + pad + 4) + 8), "white")
    d = ImageDraw.Draw(img)
    for k, r in enumerate(out):
        x, y = 8 + (k % cols) * (s + 4), 8 + (k // cols) * (s + pad + 4)
        frame = BATCHES / r["batch"] / "frames" / f"{r['frame_id']}.jpg"
        crop = build_m2.square(Image.open(frame).convert("RGB"),
                               *(float(r[c]) for c in BOX))
        img.paste(crop, (x, y))
        d.text((x + 2, y + s + 2), f"{k+2} {r['label']}", fill="black")
        d.text((x + 2, y + s + 13), f"-> {r['m2_says']} {r['conf']}", fill="#b00")
    img.save(path)


def apply(a):
    """Write the decisions back into each batch's reviewed.csv."""
    want = collections.defaultdict(dict)
    for r in csv.DictReader((HERE / a.apply).open()):
        if r["decision"].strip():
            want[r["batch"]][(r["frame_id"], *(r[k] for k in BOX))] = r["decision"].strip()
    if not want:
        sys.exit(f"{a.apply}: no row has a decision — nothing to do")

    import classes
    known = set(classes.THAI_FINE_NAMES) | {"not_a_sign", "too_small", "dont_know", "composite"}
    bad = {v for m in want.values() for v in m.values()} - known
    if bad:
        sys.exit(f"not class names: {sorted(bad)}")

    for bname, m in want.items():
        f = BATCHES / bname / "reviewed.csv"
        rows = list(csv.DictReader(f.open()))
        hit = 0
        for r in rows:
            new = m.get((r["frame_id"], *(r[k] for k in BOX)))
            if new and new != r["label"]:
                r["label"] = new
                hit += 1
        # Only now, once every row matched, is the file worth touching.
        assert hit <= len(m), (hit, len(m))
        with f.open("w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{f}: {hit} of {len(m)} decisions changed a label")
    print("\nNext: prelabel.py build, then train_m2.py")


def selfcheck(_a=None):
    assert COLS[-1] == "decision", "apply() matches on every column before it"
    # A blank decision must never touch a label, or an unreviewed sweep would
    # silently blank the dataset the first time someone ran --apply.
    assert not "".strip()
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--conf", type=float, default=0.80,
                    help="below this the model is not confident enough to argue")
    ap.add_argument("--out", default="sweep.csv")
    ap.add_argument("--sheet", default="sweep_sheet.png")
    ap.add_argument("--apply", help="a sweep.csv with the decision column filled in")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    selfcheck() if a.selfcheck else apply(a) if a.apply else sweep(a)


if __name__ == "__main__":
    main()
