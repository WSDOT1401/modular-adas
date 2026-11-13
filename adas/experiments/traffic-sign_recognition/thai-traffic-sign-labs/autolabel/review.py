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
"""
from __future__ import annotations

import argparse
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

    queue = [r["crop_id"] for r in smap if (d / "crops" / f"{r['crop_id']}.jpg").exists()]
    if only:
        queue = [c for c in queue if pred.get(c) == only]
    if todo:
        queue = [c for c in queue if c not in done]
    queue.sort(key=lambda c: (pred.get(c, "~"), c))
    if not queue:
        sys.exit("nothing to review (try without --todo, or check --only spelling)")

    print(__doc__.split("\n\n")[0])
    print(f"{len(queue)} crops.  SPACE/y accept · x not_a_sign · ? dont_know · "
          f"type to rename (TAB cycles, ENTER takes it) · b back · q save+quit")

    i, typed, pick = 0, "", 0
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
        guess = pred.get(cid, "?")
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
    print(f"\nNext: prelabel.py to-cvat {d.name.split('-')[0]}")


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
    a = ap.parse_args()
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
