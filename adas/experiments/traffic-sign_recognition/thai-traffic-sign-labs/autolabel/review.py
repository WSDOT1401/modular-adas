#!/usr/bin/env python3
"""Step 4: a human says yes or no to the VLM's guess, one crop at a time.

    review.py b01                  # every crop, grouped by what the VLM guessed
    review.py b01 --only stop      # just the ones it called `stop`
    review.py b01 --todo           # only crops nobody has confirmed yet

CVAT is where boxes get fixed. This is where names get fixed. Splitting the two
is the whole point: it lets the CVAT pass run class-agnostic, and "is this a box,
is it tight?" is a far faster question for a human than picking one of 25 names
off a dropdown while squinting at a sign 30 px wide.

Crops arrive grouped by the VLM's guess, because a wrong one is obvious next to
twenty right ones -- the same reason a contact sheet beats a spreadsheet.

``x`` (not a sign) only reaches reviewed.csv under --only. Everywhere else the
box belongs to CVAT, which showed a human the whole frame; filtered to one
class you are answering "is this KIND of thing a sign?", and the frame adds
nothing. Watch for the `!! NOT applied` line at the end -- a pass of 21 of them
was silently lost once.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import prelabel as P


def match(typed: str, names=P.NAMES) -> list[str]:
    """Class names matching what has been typed so far, best first.

    A name that STARTS with the text beats one that merely contains it, so `s`
    offers `stop` before `no_stopping_parking` -- otherwise the alphabetically
    first substring hit wins and the common case needs more keystrokes.
    """
    t = typed.lower().strip()
    if not t:
        return []
    return ([n for n in names if n.startswith(t)] +
            [n for n in names if t in n and not n.startswith(t)])


def review(d, only=None, todo=False) -> None:
    import cv2

    pred = {r["crop_id"]: r["pred"] for r in P.rows(d / "predictions.csv")}
    done = {r["crop_id"] for r in P.rows(d / "confirmed.csv")}
    smap = P.rows(P.need(d, "source_map.csv", "detect"))
    extra = fill_crops(d, smap)        # the boxes CVAT added, which have no crop yet
    if extra:
        print(f"cut {len(extra)} crop(s) for boxes added by hand in CVAT")
    smap += extra

    # After a CVAT pass, reviewed.csv is the truth -- it holds the boxes a human
    # fixed and the names chosen there. Filter and display from it, or --only
    # queues the stale pre-CVAT guess and offers up crops CVAT already deleted.
    rev, at = reviewed_rows(d, smap)
    cur = dict(pred)
    cur.update({c: rev[i]["label"] for c, i in at.items()})

    queue = [r["crop_id"] for r in smap if (d / "crops" / f"{r['crop_id']}.jpg").exists()]
    if at:
        queue = [c for c in queue if c in at]
    if only:
        queue = [c for c in queue if cur.get(c) == only]
    if todo:
        queue = [c for c in queue if c not in done]
    queue.sort(key=lambda c: (cur.get(c, "~"), c))
    if not queue:
        sys.exit("nothing to review (try without --todo, or check --only spelling)")

    print(__doc__.split("\n\n")[0])
    print(f"{len(queue)} crops.  SPACE/y accept · x not_a_sign · ? dont_know · "
          f"type to rename (TAB cycles, ENTER takes it) · b back · q save+quit")

    i, typed, pick = 0, "", 0
    # Only what gets settled in THIS run may be written back to reviewed.csv.
    # predictions.csv still holds the pre-CVAT guess for every crop nobody has
    # re-opened since, and syncing those would undo the CVAT pass wholesale.
    touched = set()
    while 0 <= i < len(queue):
        cid = queue[i]
        img = cv2.imread(str(d / "crops" / f"{cid}.jpg"))
        if img is None:
            i += 1
            continue
        s = 480 / max(img.shape[:2])
        view = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
        bar = view.copy() * 0
        cands = match(typed)
        guess = cur.get(cid, "?")
        line1 = f"[{i+1}/{len(queue)}] {guess}" + ("  (confirmed)" if cid in done else "")
        line2 = (f"> {typed}_   {cands[pick % len(cands)] if cands else 'no match'}"
                 if typed else "SPACE=yes  x=not_a_sign  b=back  q=quit")
        cv2.putText(bar, line1, (8, 24), 0, 0.6, (0, 255, 255), 1)
        cv2.putText(bar, line2, (8, 52), 0, 0.6, (255, 255, 255), 1)
        cv2.imshow("review", cv2.vconcat([view, bar[:64]]))
        k = cv2.waitKey(0) & 0xFF

        def settle(name):
            pred[cid] = name
            done.add(cid)
            touched.add(cid)
            save(d, smap, pred, done)

        if k in (ord(" "), ord("y"), 13) and not typed:
            settle(guess if guess in P.IDX else P.catch_all(
                next(r["coarse"] for r in smap if r["crop_id"] == cid)))
            i += 1
        elif k == ord("q") and not typed:
            break
        elif k == ord("b") and not typed:
            i, typed, pick = max(0, i - 1), "", 0
        elif k == ord("x") and not typed:
            settle("not_a_sign"); i += 1
        elif k == ord("?") and not typed:
            settle("dont_know"); i += 1
        elif k == 9 and cands:                       # TAB
            pick += 1
        elif k == 13 and cands:                      # ENTER
            settle(cands[pick % len(cands)])
            i, typed, pick = i + 1, "", 0
        elif k == 27:                                # ESC
            typed, pick = "", 0
        elif k in (8, 127):
            typed, pick = typed[:-1], 0
        elif 32 < k < 127:
            typed, pick = typed + chr(k), 0
    cv2.destroyAllWindows()
    save(d, smap, pred, done)
    print(f"{len(done)}/{len(queue)} confirmed -> {d/'confirmed.csv'}")
    n, refused = sync_reviewed(d, [r for r in smap if r['crop_id'] in touched],
                               pred, allow_delete=bool(only))
    if (d / "reviewed.csv").exists():
        print(f"{n} name(s) carried into {d/'reviewed.csv'}")
        if refused:
            print(f"\n  !! {len(refused)} NOT applied -- a box can only be deleted in "
                  f"CVAT, where you can see the whole frame:")
            for cid, lab in sorted(refused.items()):
                print(f"       {cid}  ({lab})")
        print("\nNext: prelabel.py build")
    else:
        print(f"\nNext: prelabel.py to-cvat {d.name.split('-')[0]}")


def reviewed_rows(d, smap):
    """(reviewed.csv rows, crop_id -> row index), or ([], {}) before a CVAT pass.

    reviewed.csv is keyed by frame and box, predictions.csv by crop, so the two
    only meet through overlap. A crop absent from the result had its box deleted
    in CVAT: it is not in the dataset, so it is not worth a reviewer's keystroke.
    """
    f = d / "reviewed.csv"
    if not f.exists():
        return [], {}
    rev = list(P.rows(f))
    by_frame = collections.defaultdict(list)
    for i, r in enumerate(rev):
        by_frame[r["frame_id"]].append(
            (i, tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2"))))
    at, taken = {}, set()
    for r in smap:
        box = tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2"))
        best, score = None, 0.0
        for i, b in by_frame.get(r["frame_id"], []):
            v = P.iou(box, b)
            if i not in taken and v > score:
                best, score = i, v
        if best is not None and score >= 0.5:
            at[r["crop_id"]] = best
            taken.add(best)
    return rev, at


def fill_crops(d, smap) -> list:
    """Crops for the boxes a human DREW in CVAT. Returns the extra smap rows.

    `prelabel.py detect` cuts one crop per box the detector proposed, and that
    is the whole of crops/. A box drawn by hand in CVAT afterwards gets a row in
    reviewed.csv and no crop on disk, so review.py could never show it -- 51 of
    b02-1's 547 boxes, and two of those were wrong. They are cut here on demand,
    the same way detect cuts its own, rather than by re-running detect, which
    would throw away every name on the batch.
    """
    import cv2

    rev, at = reviewed_rows(d, smap)
    if not rev:
        return []
    matched = set(at.values())
    crops = d / "crops"
    extra, per_frame = [], collections.Counter()
    for i, r in enumerate(rev):
        if i in matched:
            continue
        fid = r["frame_id"]
        cid = f"{fid}_c{per_frame[fid]}"
        per_frame[fid] += 1
        extra.append({"crop_id": cid, "frame_id": fid, "coarse": "",
                      **{k: r[k] for k in ("x1", "y1", "x2", "y2")}})
        out, frame = crops / f"{cid}.jpg", d / "frames" / f"{fid}.jpg"
        if out.exists() or not frame.exists():
            continue
        img = cv2.imread(str(frame))
        if img is None:
            continue
        H, W = img.shape[:2]
        patch = img[max(0, int(float(r["y1"]))):min(H, int(float(r["y2"]))),
                    max(0, int(float(r["x1"]))):min(W, int(float(r["x2"])))]
        if patch.size == 0:
            continue
        if max(patch.shape[:2]) < P.CROP_PX:          # same upscale detect uses
            s = P.CROP_PX / max(patch.shape[:2])
            patch = cv2.resize(patch, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
        crops.mkdir(exist_ok=True)
        cv2.imwrite(str(out), patch)
    return extra


def sync_reviewed(d, smap, pred, allow_delete=False) -> int:
    """Carry renames into reviewed.csv, which is what `prelabel.py build` reads.

    This file only exists after a CVAT pass, and renaming here afterwards used to
    go nowhere: review.py writes predictions.csv (keyed by crop) and build reads
    reviewed.csv (keyed by frame + box), so the two never met. Match them back by
    overlap and copy the name across.

    Names only. Boxes are left exactly as CVAT has them, and a SPECIAL is never
    written back, because CVAT showed a human the whole frame -- it is the better
    judge of where a box belongs and whether it is a sign at all. `dont_know` is
    worse still: build drops the entire frame, taking every correctly-boxed sign
    on it. So those keystrokes are refused here -- but returned, not swallowed,
    because a refusal nobody is told about is the bug this function exists to fix.

    ``allow_delete`` lets `not_a_sign` through, and review() sets it exactly when
    --only is in use. The frame argument above is about ONE box: you cannot tell
    from a 128 px crop whether that box belongs. Filtered to a single class you
    are answering a different question -- "is this KIND of thing a sign?" -- and
    the whole frame adds nothing to it. That is how the bus-stop boards were
    settled on 2026-11-16, after a pass of 21 `x` keystrokes was refused and
    silently lost. `dont_know` and the rest stay refused either way; only
    `not_a_sign` is a class-wide answer.

    Returns (names written, {crop_id: refused label}).
    """
    rev, at = reviewed_rows(d, smap)
    if not rev:
        return 0, {}
    n, refused = 0, {}
    for r in smap:
        name = pred.get(r["crop_id"], "")
        i = at.get(r["crop_id"])
        if i is None or name not in P.IDX:
            continue
        if name in P.SPECIAL and not (allow_delete and name == "not_a_sign"):
            refused[r["crop_id"]] = name
            continue
        if rev[i]["label"] != name:
            rev[i]["label"] = name
            n += 1
    if n:
        P.write_rows(d / "reviewed.csv",
                     ["frame_id", "x1", "y1", "x2", "y2", "label"],
                     [tuple(r[k] for k in ("frame_id", "x1", "y1", "x2",
                                           "y2", "label")) for r in rev])
    return n, refused


def selfcheck() -> None:
    """sync_reviewed writes the file the dataset is cut from, so it gets a check.

    Covers the three ways it can go wrong: a rename must land, a SPECIAL must not
    (CVAT is the better judge of "is this a sign"), and a crop whose box CVAT
    moved far away must not drag an unrelated box's name with it.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        P.write_rows(d / "reviewed.csv",
                     ["frame_id", "x1", "y1", "x2", "y2", "label"],
                     [("f1", "10", "10", "50", "50", "other_warning"),
                      ("f1", "200", "200", "240", "240", "information"),
                      ("f2", "10", "10", "50", "50", "other_warning")])
        smap = [{"crop_id": "c0", "frame_id": "f1", "x1": "10", "y1": "10",
                 "x2": "50", "y2": "50"},
                {"crop_id": "c1", "frame_id": "f1", "x1": "200", "y1": "200",
                 "x2": "240", "y2": "240"},
                {"crop_id": "c2", "frame_id": "f2", "x1": "900", "y1": "900",
                 "x2": "940", "y2": "940"}]
        n, refused = sync_reviewed(d, smap, {"c0": "chevron",     # renamed -> lands
                                             "c1": "not_a_sign",  # SPECIAL -> refused
                                             "c2": "chevron"})    # no overlap -> ignored
        got = [r["label"] for r in P.rows(d / "reviewed.csv")]
        assert n == 1, n
        assert got == ["chevron", "information", "other_warning"], got
        assert refused == {"c1": "not_a_sign"}, refused
        # --only: the same keystroke now lands, because the question it answers
        # is about the class, not about where this one box belongs.
        n, refused = sync_reviewed(d, smap, {"c1": "not_a_sign"}, allow_delete=True)
        assert (n, refused) == (1, {}), (n, refused)
        assert [r["label"] for r in P.rows(d / "reviewed.csv")][1] == "not_a_sign"
        # ...but the keystroke that drops a whole frame never does.
        _n, refused = sync_reviewed(d, smap, {"c0": "dont_know"}, allow_delete=True)
        assert refused == {"c0": "dont_know"}, refused
        # ...and that a reviewed box with no crop is noticed. No frames/ here,
        # so nothing is cut -- the queue drops rows whose crop is missing.
        assert [r["crop_id"] for r in fill_crops(d, smap[:2])] == ["f2_c0"]
    print("ok")


def save(d, smap, pred, done) -> None:
    P.write_rows(d / "predictions.csv", ["crop_id", "pred"],
                 sorted((r["crop_id"], pred.get(r["crop_id"], "")) for r in smap))
    # Kept apart from predictions.csv on purpose: that file means "the VLM's best
    # guess", this one means "a human looked". Merging them would lose the
    # difference, and the difference is the only reason to trust the labels.
    P.write_rows(d / "confirmed.csv", ["crop_id"], sorted((c,) for c in done))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bid")
    ap.add_argument("--only", help="only crops the VLM gave this class")
    ap.add_argument("--todo", action="store_true", help="skip already-confirmed crops")
    ap.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    review(P.find(a.bid), a.only, a.todo)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        assert match("sto")[0] == "stop", "prefix hit comes first"
        assert match("sto") == ["stop", "no_stopping_parking"], match("sto")
        assert match("s")[0] == "stop", "a prefix hit must beat a substring hit"
        assert match("") == [] and match("zzz") == []
        assert match("turn")[:2] == ["turn_left", "turn_right"], match("turn")
        assert "no_left_turn" in match("turn"), "substring hits still offered, later"
        print("ok")
    else:
        main()
