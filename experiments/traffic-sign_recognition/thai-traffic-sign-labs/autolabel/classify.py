"""[3b] Ask a VLM to name each sign, then grade it against the gold answer key.

    (Colab, needs a GPU)   python classify.py run   --dir work/gold --out work/predictions.csv
    (your laptop, no GPU)  python classify.py score --dir work/gold --pred work/predictions.csv
    (anywhere)             python classify.py selfcheck

Split in two on purpose: ``run`` needs ~6 GB of VRAM, ``score`` needs stdlib.
You can re-grade a finished run as often as you like without touching a GPU.

WHY THE METRIC IS MACRO-RECALL AND NOT ACCURACY
-----------------------------------------------
``information`` is 56% of the answer key, and once the crop's coarse class is
known the Information parent offers only two choices. So a program that never
opens the image -- "Information -> information, Warning -> other_warning,
Regulatory -> no_stopping_parking" -- scores 77% accuracy. Any accuracy figure
below that is worse than blind guessing, and one slightly above it has measured
nothing. ``score`` therefore prints that baseline on the same line as every
number it reports, and leads with macro-recall (each class weighted equally),
where the blind program scores 33%.

Classes with fewer than MIN_SUPPORT examples are listed but excluded from the
macro average: ``stop`` has exactly one crop, and one crop cannot produce a
percentage. Fix that with footage, not with arithmetic.
"""
from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re
import sys

_repo = pathlib.Path(__file__).resolve().parents[2]
if (_repo / "classes.py").exists():   # repo layout; in the Colab zip classes.py sits alongside
    sys.path.insert(0, str(_repo))
import classes  # noqa: E402

MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
ABSTAIN = "unclear"

# Prompt v2 (2026-10-04). v1 gave the model bare snake_case names and nothing
# else, while the human annotators had the classes.py comments and their own
# settlement rules -- an unfair comparison, not a model limitation.
#
# These lines are written from the gold crops themselves (one contact sheet of
# three examples per class), NOT from v1's error list. Describing only the
# classes that failed would be tuning the prompt against the test set, and the
# score would stop measuring the model. Two of them contradict European
# convention and would have been wrong from memory: keep_left_or_right is a
# yellow diamond here, and turn_left/turn_right are red-ringed white circles.
LOOKS_LIKE = {
    "stop": "red octagon with white text",
    "no_left_turn": "white circle, red ring, black left-turn arrow struck through by a red diagonal",
    "no_right_turn": "white circle, red ring, black right-turn arrow struck through by a red diagonal",
    "no_right_u_turn": "white circle, red ring, black U-turn arrow struck through by a red diagonal",
    "no_stopping_parking": "plain blue circle with a red ring and either a single red diagonal slash "
                           "(no parking) or a red X (no stopping); no arrow or symbol inside",
    "speed_limit": "white circle, red ring, one large black number; sometimes on a yellow backing board",
    "keep_left": "blue circle with a white arrow pointing left",
    "keep_right": "blue circle with a white arrow pointing right",
    "keep_left_or_right": "yellow diamond with two black arrows, one pointing down-left and one "
                          "down-right (pass on either side)",
    "turn_left": "white circle, red ring, black arrow turning left",
    "turn_right": "white circle, red ring, black arrow turning right",
    "reserved_for_bus": "blue sign showing a white bus",
    "left_curve": "yellow diamond, a single black arrow bending to the left",
    "right_curve": "yellow diamond, a single black arrow bending to the right",
    "t_junction_left": "yellow diamond, black T-shaped junction with the side road going left",
    "t_junction_right": "yellow diamond, black T-shaped junction with the side road going right",
    "pedestrian_crossing": "a walking figure on a crossing: either a blue square with a white figure, "
                           "or a yellow-green diamond with a black figure",
    "u_turn": "blue square with a white U-turn arrow, often with a small plate underneath",
    "information": "large green or blue rectangular board with place names, text and direction arrows",
}
# Below this, a per-class recall is one or two crops wide and reports noise.
MIN_SUPPORT = 5
# Qwen2.5-VL picks its own input resolution and the default SHRINKS a 448px
# crop. For a sign whose whole identity is a small glyph that is fatal, and it
# fails silently -- you just get bad numbers. Floor it at the crop's own size.
# ponytail: fixed window because every crop is ~448px; revisit if crops.py
# starts emitting mixed sizes.
MIN_PIXELS, MAX_PIXELS = 448 * 448, 896 * 896


def read_key(root: pathlib.Path, required: bool = True) -> dict[str, str]:
    path = root / "answer_key.csv"
    if not path.exists():
        if required:
            sys.exit(f"{path} not found — run `python gold.py score` first")
        return {}
    return {r["crop_id"]: r["label"] for r in csv.DictReader(path.open())}


def parents(root: pathlib.Path, key: dict[str, str], crops=None) -> dict[str, str]:
    """Coarse class per crop: from the human label, else the detector's guess.

    Which source is used is the difference between the two things this script
    does, and it is worth being explicit about:

    * **Measuring** (crops in the key) uses the *human* coarse label. In the real
      pipeline a person fixes the coarse class during review, so that is what the
      VLM would see. Feeding the detector's guess instead would leave you unable
      to say whether a bad score was the VLM's fault or the detector's.
    * **Pre-annotating** (``--unlabelled``, crops nobody has judged yet) has no
      human label to use, so it falls back to the detector — which is right 91.2%
      of the time. Those 8.8% reach the reviewer with the wrong option list, and
      that is a real cost of pre-annotation, not a bug.
    """
    detector = {r["crop_id"]: r["coarse"]
                for r in csv.DictReader((root / "source_map.csv").open())}
    out = {c: classes.THAI_FINE_PARENT.get(key.get(c, "")) or detector.get(c)
           for c in (key if crops is None else crops)}
    missing = [c for c, p in out.items() if p not in classes.THAI_FINE_BY_PARENT]
    if missing:
        sys.exit(f"no coarse class for {len(missing)} crops, e.g. {missing[:3]}")
    return out


def catch_all(parent: str) -> str:
    """The "not on this list" option for a parent.

    Regulatory and Warning have an explicit ``other_*``; Information does not --
    classes.py makes ``information`` itself the catch-all and says to keep it
    last. v2 built this name mechanically as ``"other_" + parent.lower()`` and so
    offered Qwen ``other_information``, a class that does not exist. 80 of the
    209 Information crops came back as it, and the substring parser below scored
    every one of them as a confident ``information``. Both halves of that bug are
    asserted in selfcheck.
    """
    group = classes.THAI_FINE_BY_PARENT[parent]
    return next((o for o in group if o.startswith("other_")), group[-1])


def prompt_for(parent: str) -> str:
    other = catch_all(parent)
    lines = [f"- {o}: {LOOKS_LIKE[o]}"
             for o in classes.THAI_FINE_BY_PARENT[parent] if o != other]
    shown = LOOKS_LIKE.get(other)
    lines += [f"- {other}: " + (f"{shown}; also use this for any other {parent} sign that is "
                                "not one of the above" if shown else
                                f"a clear {parent} sign that is not exactly one of the above"),
              f"- {ABSTAIN}: too small, blurry or obscured to read"]
    # The closing rule targets v1's dominant failure: Qwen almost never picked a
    # catch-all (4 of 78), preferring to name the nearest specific sign. Naming
    # the behaviour is the fix; listing the option was not enough.
    # "an Information", "a Regulatory": the vowel rule touches only the
    # Information prompt, so Regulatory and Warning stay byte-identical to v2
    # and their v3 results double as a consistency check on the run.
    art = "an" if parent[0] in "AEIOU" else "a"
    return (f"This photo is a Thai road sign, already known to be {art} {parent} sign.\n\n"
            "Which sign is it? Reply with exactly one name from this list and "
            "nothing else:\n\n" + "\n".join(lines) +
            f"\n\nRule: if the sign does not match one of the descriptions above, "
            f"answer {other}. Do not pick the closest match — a sign that merely "
            f"resembles an option, without matching its description, is {other}.")


def parse_answer(raw: str, parent: str) -> str:
    """Longest option name present in the reply, else 'unparsed'.

    Longest-first matters: 'no_right_u_turn' contains 'no_right_turn' as a
    near-miss and 'keep_left_or_right' contains 'keep_left'. Shortest-first
    would silently mislabel every one of them.
    """
    low = raw.lower()
    opts = sorted(classes.THAI_FINE_BY_PARENT[parent] + (ABSTAIN,), key=len, reverse=True)
    for o in opts:
        # Word boundaries, not `in`: "other_information" contains "information"
        # and a bare substring test silently scored 80 refusals as confident
        # answers. "_" is a word character, so \b also separates keep_left from
        # keep_left_or_right and no_right_turn from no_right_u_turn.
        if re.search(rf"\b{re.escape(o)}\b", low):
            return o
    return "unparsed"


# ------------------------------------------------------------------ run (GPU) --
def cmd_run(args):
    import torch  # noqa: PLC0415 — GPU-only; keep `score` importable on a laptop
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
    from PIL import Image

    root, out = args.dir, args.out
    key = read_key(root, required=not args.unlabelled)
    if args.unlabelled:
        # The crops that need a label are exactly the ones the answer key has no
        # opinion on. Running over the key instead would re-predict work humans
        # have already settled, and predict nothing for the new footage.
        seen = {r["crop_id"] for r in csv.DictReader((root / "source_map.csv").open())}
        want = sorted(seen - set(key))
        print(f"pre-annotating {len(want)} crops with no human label "
              f"({len(key)} already settled, skipped)")
    else:
        want = sorted(key)
    parent = parents(root, key, want)
    crops = args.crops or (root / "crops")

    done = {}
    if out.exists():   # Colab kills idle sessions; don't lose 20 minutes to one.
        done = {r["crop_id"]: r for r in csv.DictReader(out.open())}
        print(f"resuming: {len(done)} already predicted")
    todo = [c for c in want if c not in done]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        sys.exit(f"nothing to do — {out} already covers every crop")

    print(f"loading {args.model} in 4-bit …")
    proc = AutoProcessor.from_pretrained(args.model, min_pixels=MIN_PIXELS,
                                         max_pixels=MAX_PIXELS)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, device_map="auto",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            # fp16, not bf16: the free Colab T4 is Turing and has no bf16 units.
            bnb_4bit_compute_dtype=torch.float16))
    model.eval()

    fh = out.open("a" if done else "w", newline="")
    w = csv.writer(fh)
    if not done:
        w.writerow(["crop_id", "parent", "pred", "raw"])

    for i, crop in enumerate(todo, 1):
        img = Image.open(crops / f"{crop}.jpg").convert("RGB")
        msgs = [{"role": "user", "content": [
            {"type": "image"}, {"type": "text", "text": prompt_for(parent[crop])}]}]
        text = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        inputs = proc(text=[text], images=[img], return_tensors="pt").to(model.device)

        if i == 1:   # prove the resize floor took effect before burning 25 min
            h, ww = inputs["image_grid_thw"][0][1:].tolist()
            seen, have = ww * 14 * h * 14, img.size[0] * img.size[1]
            # Only shrinking matters. Upscaling invents no detail but destroys
            # none either; downscaling throws away the glyph that IS the answer.
            verdict = ("OK" if seen >= have * 0.98 else
                       "STOP — Qwen is shrinking the crops, this run is worthless")
            print(f"  crop 1: file {img.size[0]}x{img.size[1]} -> model sees "
                  f"{ww * 14}x{h * 14} px  ({seen / have:.2f}x area) {verdict}")

        with torch.inference_mode():
            gen = model.generate(**inputs, max_new_tokens=16, do_sample=False)
        raw = proc.decode(gen[0][inputs["input_ids"].shape[1]:],
                          skip_special_tokens=True).strip()
        w.writerow([crop, parent[crop], parse_answer(raw, parent[crop]), raw])
        fh.flush()
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}")
    fh.close()
    print(f"\nwrote {out} — now run:  python classify.py score --pred {out}")


# ---------------------------------------------------------------------- score --
def tally(key: dict[str, str], pred: dict[str, str], min_support: int = MIN_SUPPORT) -> dict:
    """Grade predictions against the key. Pure, so selfcheck can assert on it."""
    real = {c: l for c, l in key.items() if l in classes.THAI_FINE_PARENT}

    # The blind baseline: per parent, always answer that parent's commonest class.
    by_parent = collections.defaultdict(collections.Counter)
    for label in real.values():
        by_parent[classes.THAI_FINE_PARENT[label]][label] += 1
    blind = {p: c.most_common(1)[0][0] for p, c in by_parent.items()}

    n_c = collections.Counter(real.values())
    hit_c = collections.Counter(l for c, l in real.items() if pred.get(c) == l)
    scored = sorted(c for c in n_c if n_c[c] >= min_support)

    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    return {
        "n": len(real),
        "missing": [c for c in real if c not in pred],
        "acc": mean([1.0 if pred.get(c) == l else 0.0 for c, l in real.items()]),
        "blind_acc": mean([1.0 if blind[classes.THAI_FINE_PARENT[l]] == l else 0.0
                           for l in real.values()]),
        "macro": mean([hit_c[c] / n_c[c] for c in scored]),
        "blind_macro": mean([1.0 if blind[classes.THAI_FINE_PARENT[c]] == c else 0.0
                             for c in scored]),
        "scored": scored,
        "n_c": n_c,
        "hit_c": hit_c,
        "confusion": collections.Counter(
            (l, pred.get(c, "MISSING")) for c, l in real.items() if pred.get(c) != l),
    }


def cmd_score(args):
    key = read_key(args.dir)
    rows = list(csv.DictReader(args.pred.open()))
    pred = {r["crop_id"]: r["pred"] for r in rows}
    t = tally(key, pred)
    if t["missing"]:
        print(f"!! {len(t['missing'])} key crops have no prediction "
              f"(scored as wrong), e.g. {t['missing'][:3]}\n")

    print(f"=== {args.pred.name} vs answer_key.csv — {t['n']} crops ===\n")
    print(f"  macro-recall  {t['macro']:6.1%}   (blind baseline {t['blind_macro']:.1%})"
          f"   <- the headline, {len(t['scored'])} classes with n>={MIN_SUPPORT}")
    print(f"  accuracy      {t['acc']:6.1%}   (blind baseline {t['blind_acc']:.1%})"
          "   <- do not quote without the baseline\n")
    verdict = ("no better than a program that never opens the image"
               if t["macro"] <= t["blind_macro"] else
               "reads some signs, not enough to auto-label — report as a negative result"
               if t["macro"] <= 0.50 else
               "worth building steps 3b-5 around")
    print(f"  verdict: {verdict}\n")

    print("  per class (* = excluded from macro, too few to measure):")
    for parent, group in classes.THAI_FINE_BY_PARENT.items():
        for c in group:
            n = t["n_c"].get(c, 0)
            if not n:
                continue
            mark = " " if c in t["scored"] else "*"
            print(f"   {mark}{parent:12s} {c:22s} {t['hit_c'][c]:3d}/{n:<3d} "
                  f"{t['hit_c'][c] / n:5.0%}")

    print("\n  worst confusions (true -> predicted):")
    for (true, got), k in t["confusion"].most_common(8):
        print(f"    {k:3d}  {true} -> {got}")

    raw = collections.Counter(r["pred"] for r in rows)
    print(f"\n  abstained {raw[ABSTAIN]}, unparseable {raw['unparsed']}"
          " (both scored as wrong)")
    small = [c for c, l in key.items() if l == "too_small"]
    if small:
        ok = sum(1 for c in small if pred.get(c) == ABSTAIN)
        print(f"  knew to shut up on {ok}/{len(small)} too_small crops "
              "(anecdote, not a measurement)")
    for c, l in sorted(key.items()):
        if l == "stop":
            hit = "FOUND IT" if pred.get(c) == "stop" else f"missed — said '{pred.get(c)}'"
            print(f"\n  the one stop sign ({c}): {hit}")


def cmd_selfcheck(args):
    """Fails if the metric breaks. The metric is the deliverable, so it is what gets tested."""
    key = dict.fromkeys("abc", "information") | {
        "d": "u_turn", "e": "pedestrian_crossing",
        "f": "pedestrian_crossing", "g": "other_warning"}
    # blind would score 5/7 acc (information x3 + pedestrian_crossing x2) and
    # 2/4 macro; this prediction gets u_turn right and other_warning wrong.
    pred = key | {"g": ABSTAIN}
    t = tally(key, pred, min_support=1)
    assert t["n"] == 7, t["n"]
    assert abs(t["acc"] - 6 / 7) < 1e-9, t["acc"]
    assert abs(t["blind_acc"] - 5 / 7) < 1e-9, t["blind_acc"]
    assert abs(t["macro"] - 0.75) < 1e-9, t["macro"]
    assert abs(t["blind_macro"] - 0.50) < 1e-9, t["blind_macro"]
    assert t["confusion"][("other_warning", ABSTAIN)] == 1
    assert parse_answer("I think it is no_right_u_turn.", "Regulatory") == "no_right_u_turn"
    assert parse_answer("keep_left_or_right", "Regulatory") == "keep_left_or_right"
    assert parse_answer("keep_left", "Regulatory") == "keep_left"
    assert parse_answer("a blue rectangle", "Warning") == "unparsed"
    # The v2 bug, both halves: the prompt must not invent a class, and an
    # invalid reply must surface as unparsed rather than substring-match one.
    assert catch_all("Information") == "information", catch_all("Information")
    assert catch_all("Warning") == "other_warning"
    assert catch_all("Regulatory") == "other_regulatory"
    assert "other_information" not in prompt_for("Information")
    assert parse_answer("other_information", "Information") == "unparsed"
    print("selfcheck ok")


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
for name, fn in (("run", cmd_run), ("score", cmd_score), ("selfcheck", cmd_selfcheck)):
    s = sub.add_parser(name)
    if name != "selfcheck":
        s.add_argument("--dir", type=pathlib.Path, default=pathlib.Path("work/gold"))
        s.add_argument("--pred" if name == "score" else "--out", dest="pred" if name == "score" else "out",
                       type=pathlib.Path, default=pathlib.Path("work/predictions.csv"))
    if name == "run":
        s.add_argument("--crops", type=pathlib.Path,
                       help="default <dir>/crops; point at crops_ctx for the context ablation")
        s.add_argument("--model", default=MODEL)
        s.add_argument("--limit", type=int, help="first N crops only, for a smoke test")
    if name == "run":
        s.add_argument("--unlabelled", action="store_true",
                       help="pre-annotate crops NOT in the answer key (new footage). "
                            "Without it, run only re-predicts the key, to measure.")
    s.set_defaults(fn=fn)
args = ap.parse_args()
args.fn(args)
