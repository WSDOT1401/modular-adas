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
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import classes  # noqa: E402

# Not classes — dispositions. Kept out of classes.py because they never reach a
# model: they mark crops to exclude, fix, or expect an abstention on.
#   too_small  = it IS a sign, nobody could read it -> VLM should abstain
#   dont_know  = legible, but you don't recognise it -> LOOK IT UP, must end empty
#   not_a_sign = detector false positive -> dropped before scoring
#   composite  = the box holds a sign *assembly*, not a sign (a school-zone
#                banner containing a 30 roundel, a board of three per-vehicle
#                limits). The box is wrong, not the reading -- forcing it into
#                speed_limit teaches "orange banner = speed limit", forcing it
#                into not_a_sign teaches the opposite. Split it at step 2.
SPECIAL = ("too_small", "dont_know", "not_a_sign", "composite")
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


def _merge(src: pathlib.Path, root: pathlib.Path) -> None:
    """Fold a track.py output directory into the gold workspace.

    Crop ids are clip+track derived, so a crop already here is the same picture
    and is left alone rather than overwritten -- re-running a clip is a no-op,
    not a silent swap underneath someone's labels."""
    src_tracks = json.loads((src / "tracks.json").read_text())
    have = {t["crop_id"] for t in json.loads((root / "tracks.json").read_text())}
    # labelable is the --min-best-side verdict: a track whose closest view is
    # still too small has no crop anyone could name. Honour it here too, or a
    # merge quietly re-admits exactly what that filter excluded.
    fresh = [t for t in src_tracks
             if t.get("crop_id") and t.get("labelable", True)
             and t["crop_id"] not in have]
    if not fresh:
        print(f"{src}: nothing new")
        return

    for sub in ("crops", "crops_ctx"):
        (root / sub).mkdir(parents=True, exist_ok=True)
        for t in fresh:
            f = src / sub / f"{t['crop_id']}.jpg"
            if f.exists():
                shutil.copy(f, root / sub / f.name)

    merged = json.loads((root / "tracks.json").read_text()) + fresh
    (root / "tracks.json").write_text(json.dumps(merged, indent=1))

    new_file = not (root / "source_map.csv").exists()
    with (root / "source_map.csv").open("a", newline="") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["crop_id", "clip", "track_id", "coarse", "peak_px",
                        "n_dets", "flips_class"])
        for t in fresh:
            w.writerow([t["crop_id"], t["clip"], t["track_id"], t["coarse"],
                        round(t["peak"]["size"]), t["n_dets"], t["flips_class"]])
    clips = {t["clip"] for t in fresh}
    print(f"{src}: +{len(fresh)} crops from {len(clips)} clip(s)")


def cmd_add(args):
    """Queue crops a labeller has not seen, leaving finished work alone.

    ``init`` copies every crop into ``_unsorted``, so running it again after a
    second batch of footage would re-queue crops already labelled. This only
    adds what is genuinely new, per person, so labelling stays incremental."""
    root = args.dir
    if args.src:
        _merge(args.src, root)
    crops = sorted((root / "crops").glob("*.jpg"))
    if not crops:
        sys.exit(f"no crops in {root/'crops'}")
    people = sorted(p for p in (root / "labels").iterdir() if p.is_dir())
    if not people:
        sys.exit(f"no annotator folders in {root/'labels'} — run init first")

    for who in people:
        for folder in (*classes.THAI_FINE_NAMES, *SPECIAL):
            (who / folder).mkdir(parents=True, exist_ok=True)   # new classes too
        seen = {f.stem for f in who.rglob("*.jpg")}
        new = [c for c in crops if c.stem not in seen]
        for c in new:
            shutil.copy(c, who / PILE / c.name)
        done = len(seen) - len(list((who / PILE).glob("*.jpg"))) + len(new)
        print(f"  {who.name}: +{len(new)} new   "
              f"({len(list((who/PILE).glob('*.jpg')))} queued, {done} already labelled)")


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


def cmd_sheet(args):
    """One PNG of every disagreement, captioned with who said what.

    The partner is remote, so settling means a video call: a contact sheet is
    the thing you can both point at. Reads disagreements.csv, so run score first.
    """
    from PIL import Image, ImageDraw

    root = args.dir
    rows = list(csv.DictReader((root / "disagreements.csv").open()))
    if not rows:
        sys.exit("no disagreements.csv — run `gold.py score` first")
    a, b = list(rows[0])[1:3]
    rows.sort(key=lambda r: (r[a], r[b]))  # same dispute lands side by side

    cell, cap, cols = 200, 46, 6
    rowsn = -(-len(rows) // cols)
    sheet = Image.new("RGB", (cols * cell, rowsn * (cell + cap)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, r in enumerate(rows):
        x, y = (i % cols) * cell, (i // cols) * (cell + cap)
        crop = Image.open(root / "crops" / f"{r['crop_id']}.jpg")
        crop.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
        sheet.paste(crop, (x + (cell - crop.width) // 2, y + (cell - crop.height) // 2))
        draw.rectangle([x, y, x + cell - 1, y + cell + cap - 1], outline="#ccc")
        draw.text((x + 5, y + cell + 2), f"{i+1}. {r['crop_id'][-9:]}", fill="#888")
        draw.text((x + 5, y + cell + 14), f"{a[:7]}: {r[a]}", fill="#b00")
        draw.text((x + 5, y + cell + 26), f"{b[:7]}: {r[b]}", fill="#00b")

    out = root / "disagreements.png"
    sheet.save(out)
    print(f"{out}  —  {len(rows)} crops, numbered 1-{len(rows)} in reading order")
    print(f"red = {a}, blue = {b}")
    print(f"\nGo through them on a call, then write the agreed label for each "
          f"number into\n  {root / 'settled.txt'}\n"
          f"one per line, e.g. `1 not_a_sign`. Then: python gold.py apply")


def cmd_apply(args):
    """Write the settled labels into both people's folders, then score again."""
    root = args.dir
    rows = list(csv.DictReader((root / "disagreements.csv").open()))
    a, b = list(rows[0])[1:3]      # hoisted: list.sort empties the list during the key call
    rows.sort(key=lambda r: (r[a], r[b]))   # must match cmd_sheet's order exactly
    settled = root / "settled.txt"
    if not settled.exists():
        sys.exit(f"write the agreed labels into {settled} first (see `gold.py sheet`)")

    people = sorted(p for p in (root / "labels").iterdir() if p.is_dir())
    moved = 0
    for line in settled.read_text().split("\n"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        # tolerant on purpose: this file is edited by hand during a call, and
        # notes get wrapped around the pair rather than after a '#'.
        m = re.search(r"(\d+)\s+([a-z_]+)\s*$", line)
        if not m:
            sys.exit(f"{settled}: cannot read '{line}' — want '<number> <class>'")
        num, label = m.groups()
        if label not in KNOWN or label == PILE:
            sys.exit(f"{settled}: '{label}' is not a class. Not guessing.")
        cid = rows[int(num) - 1]["crop_id"]
        for person in people:
            hits = list(person.glob(f"*/{cid}.jpg"))
            if not hits:
                sys.exit(f"{cid} not found under {person.name} — folders moved?")
            if hits[0].parent.name != label:
                (person / label).mkdir(exist_ok=True)
                shutil.move(hits[0], person / label / f"{cid}.jpg")
                moved += 1
    print(f"settled {moved} files across {len(people)} labellers — re-run `gold.py score`")


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

    key = [(c, la[c]) for c in agree
           if la[c] not in ("not_a_sign", "dont_know", "composite")]
    dropped = sum(1 for c in agree if la[c] == "not_a_sign")
    comp = sum(1 for c in agree if la[c] == "composite")
    with (root / "answer_key.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["crop_id", "label"]); w.writerows(key)
    with (root / "disagreements.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["crop_id", a.name, b.name])
        w.writerows((c, la[c], lb[c]) for c in both if la[c] != lb[c])

    dist = collections.Counter(l for _, l in key)
    small = dist.get("too_small", 0)
    print(f"\nanswer_key.csv: {len(key)} crops"
          f"   (excluded {dropped} not_a_sign = detector false positives"
          + (f", {comp} composite = boxes holding >1 sign" if comp else "") + ")")
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
for name, fn in (("init", cmd_init), ("add", cmd_add), ("score", cmd_score),
                 ("sheet", cmd_sheet), ("apply", cmd_apply)):
    s = sub.add_parser(name)
    s.add_argument("--dir", type=pathlib.Path, default=pathlib.Path("work/gold"))
    if name == "init":
        s.add_argument("--annotators", default="annotator_a,annotator_b")
    if name == "add":
        s.add_argument("--from", dest="src", type=pathlib.Path,
                       help="a track.py output dir to fold in first")
    s.set_defaults(fn=fn)
args = ap.parse_args()
args.fn(args)
