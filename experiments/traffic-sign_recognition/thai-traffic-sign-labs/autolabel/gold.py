"""[0] Gold set: make the labelling folders, then score what came out of them.

The folder name IS the label, so the folders are generated from classes.py
rather than typed by hand — a typo'd folder would silently become a new class.

    python gold.py init  --dir work/gold --annotators rachata,friend
    python gold.py score --dir work/gold

Each annotator gets their own copy of the crops in ``_unsorted/`` and drags each
one into a class folder. Finder *moves* files within a volume, so the copies are
per-annotator on purpose: otherwise the first person to label would empty the
pile for the second. When ``_unsorted/`` is empty you are done.

Both people label all 141, independently. How often you agree is the ceiling for
any model score — a VLM cannot meaningfully beat two humans who only agree 85%
of the time.
"""
from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import classes  # noqa: E402

# Not classes — dispositions. Kept out of classes.py because they never reach a
# model: they mark crops to exclude, fix, or expect an abstention on.
#   too_small  = it IS a sign, nobody could read it -> VLM should abstain
#   dont_know  = legible, but you don't recognise it -> LOOK IT UP, must end empty
#   not_a_sign = detector false positive -> dropped before scoring
SPECIAL = ("too_small", "dont_know", "not_a_sign")
PILE = "_unsorted"


def cmd_init(args):
    root = args.dir
    crops = sorted((root / "crops").glob("*.jpg"))
    if not crops:
        sys.exit(f"no crops in {root/'crops'}")
    names = [a.strip() for a in args.annotators.split(",") if a.strip()]
    if len(names) < 2:
        sys.exit("need at least 2 annotators — the agreement rate is the point")

    for who in names:
        base = root / "labels" / who
        if base.exists() and any((base / PILE).glob("*.jpg")):
            print(f"  {who}: already started, leaving alone")
            continue
        for folder in (PILE, *classes.THAI_FINE_NAMES, *SPECIAL):
            (base / folder).mkdir(parents=True, exist_ok=True)
        for c in crops:
            shutil.copy(c, base / PILE / c.name)
        print(f"  {who}: {len(classes.THAI_FINE_NAMES)}+{len(SPECIAL)} folders, "
              f"{len(crops)} crops in {PILE}/")

    print(f"\nDrag each crop out of {PILE}/ into the folder for what it is.")
    print("Use too_small if nobody could read it. Use dont_know if YOU can't "
          "name it — then look it up; that folder must be empty at the end.")
    print(f"\nWhen both are done:  python gold.py score --dir {root}")


KNOWN = set(classes.THAI_FINE_NAMES) | set(SPECIAL) | {PILE}


def _read(base: pathlib.Path) -> dict[str, str]:
    """Folder name -> label. A folder that is not a known class is fatal: it
    would otherwise land an unknown class in answer_key.csv and only surface
    much later, as a training or prompting bug."""
    out, unknown = {}, []
    for folder in sorted(base.iterdir()):
        if not folder.is_dir() or folder.name == PILE:
            continue
        if folder.name not in KNOWN:
            unknown.append((folder.name, len(list(folder.glob("*.jpg")))))
            continue
        for f in folder.glob("*.jpg"):
            out[f.stem] = folder.name
    if unknown:
        listing = ", ".join(f"{n} ({c} crops)" for n, c in unknown)
        sys.exit(f"{base.name}: folder(s) not in classes.py -> {listing}\n"
                 "Either add the class to THAI_FINE_BY_PARENT, or move those "
                 "crops into an existing folder. Not guessing.")
    return out


def cmd_score(args):
    root = args.dir
    people = sorted(p for p in (root / "labels").iterdir() if p.is_dir())
    if len(people) < 2:
        sys.exit("need 2 labelled folders")
    a, b = people[0], people[1]
    la, lb = _read(a), _read(b)

    left = len(list((a / PILE).glob("*.jpg"))) + len(list((b / PILE).glob("*.jpg")))
    if left:
        print(f"!! {left} crops still in {PILE}/ — finish labelling first\n")
    for who, lab in ((a, la), (b, lb)):
        n = sum(v == "dont_know" for v in lab.values())
        if n:
            print(f"!! {who.name} has {n} crops in dont_know/ — look them up, "
                  "they cannot go in the answer key\n")

    both = sorted(set(la) & set(lb))
    agree = [c for c in both if la[c] == lb[c]]
    print(f"labelled by both: {len(both)}")
    print(f"agreed:           {len(agree)}  ({100*len(agree)/max(len(both),1):.1f}%)"
          "   <- your human ceiling")
    print(f"disagreed:        {len(both)-len(agree)}")

    key = [(c, la[c]) for c in agree if la[c] not in ("not_a_sign", "dont_know")]
    dropped = sum(1 for c in agree if la[c] == "not_a_sign")
    with (root / "answer_key.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["crop_id", "label"]); w.writerows(key)
    with (root / "disagreements.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["crop_id", a.name, b.name])
        w.writerows((c, la[c], lb[c]) for c in both if la[c] != lb[c])

    dist = collections.Counter(l for _, l in key)
    small = dist.get("too_small", 0)
    print(f"\nanswer_key.csv: {len(key)} crops"
          f"   (excluded {dropped} not_a_sign = detector false positives)")
    print(f"disagreements.csv: {len(both)-len(agree)} to settle together, "
          "then re-run score")

    print("\nper-class counts in the answer key:")
    for name in classes.THAI_FINE_NAMES + ["too_small"]:
        n = dist.get(name, 0)
        flag = "  <- none" if n == 0 else ""
        print(f"  {name:26s} {n:3d}{flag}")

    if len(key) and small / len(key) > 0.20:
        print(f"\n!! {100*small/len(key):.0f}% is too_small (>20%). Fix frame "
              "selection in step 1 before scoring any VLM, or you are measuring "
              "your crops, not the model.")
    empty = [n for n in classes.THAI_FINE_NAMES if dist.get(n, 0) == 0]
    if empty:
        print(f"\n{len(empty)}/{len(classes.THAI_FINE_NAMES)} classes have zero "
              "examples here. Expect them to be rare overall — consider merging "
              "them into an other_* bucket:")
        print("  " + ", ".join(empty))


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
for name, fn in (("init", cmd_init), ("score", cmd_score)):
    s = sub.add_parser(name)
    s.add_argument("--dir", type=pathlib.Path, default=pathlib.Path("work/gold"))
    if name == "init":
        s.add_argument("--annotators", default="annotator_a,annotator_b")
    s.set_defaults(fn=fn)
args = ap.parse_args()
args.fn(args)
