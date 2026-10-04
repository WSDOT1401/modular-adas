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
import sys

_repo = pathlib.Path(__file__).resolve().parents[2]
if (_repo / "classes.py").exists():   # repo layout; in the Colab zip classes.py sits alongside
    sys.path.insert(0, str(_repo))
import classes  # noqa: E402

MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
ABSTAIN = "unclear"
# Below this, a per-class recall is one or two crops wide and reports noise.
MIN_SUPPORT = 5
# Qwen2.5-VL picks its own input resolution and the default SHRINKS a 448px
# crop. For a sign whose whole identity is a small glyph that is fatal, and it
# fails silently -- you just get bad numbers. Floor it at the crop's own size.
# ponytail: fixed window because every crop is ~448px; revisit if crops.py
# starts emitting mixed sizes.
MIN_PIXELS, MAX_PIXELS = 448 * 448, 896 * 896


def read_key(root: pathlib.Path) -> dict[str, str]:
    path = root / "answer_key.csv"
    if not path.exists():
        sys.exit(f"{path} not found — run `python gold.py score` first")
    return {r["crop_id"]: r["label"] for r in csv.DictReader(path.open())}


def parents(root: pathlib.Path, key: dict[str, str]) -> dict[str, str]:
    """Coarse class per crop: from the human label, else the detector's guess.

    The human label is the honest source — in the real pipeline step 2 is a
    person fixing the coarse class in CVAT, so that is what the VLM would see.
    Only the handful of crops with no fine label (``too_small``) fall back to
    source_map, purely so they can still be shown and scored as abstentions.
    """
    detector = {r["crop_id"]: r["coarse"]
                for r in csv.DictReader((root / "source_map.csv").open())}
    out = {}
    for crop, label in key.items():
        out[crop] = classes.THAI_FINE_PARENT.get(label) or detector.get(crop)
    missing = [c for c, p in out.items() if p not in classes.THAI_FINE_BY_PARENT]
    if missing:
        sys.exit(f"no coarse class for {len(missing)} crops, e.g. {missing[:3]}")
    return out


def prompt_for(parent: str) -> str:
    opts = classes.THAI_FINE_BY_PARENT[parent]
    lines = [f"- {o}" for o in opts if not o.startswith("other_")]
    lines += [f"- other_{parent.lower()}  (clearly a {parent} sign, but not one of the above)",
              f"- {ABSTAIN}  (too small or too blurry to read)"]
    return (f"This photo is a Thai road sign. It is already known to be a "
            f"{parent} sign.\n\nWhich sign is it? Reply with exactly one name "
            "from this list and nothing else:\n\n" + "\n".join(lines))


def parse_answer(raw: str, parent: str) -> str:
    """Longest option name present in the reply, else 'unparsed'.

    Longest-first matters: 'no_right_u_turn' contains 'no_right_turn' as a
    near-miss and 'keep_left_or_right' contains 'keep_left'. Shortest-first
    would silently mislabel every one of them.
    """
    low = raw.lower()
    opts = sorted(classes.THAI_FINE_BY_PARENT[parent] + (ABSTAIN,), key=len, reverse=True)
    for o in opts:
        if o in low:
            return o
    return "unparsed"


# ------------------------------------------------------------------ run (GPU) --
def cmd_run(args):
    import torch  # noqa: PLC0415 — GPU-only; keep `score` importable on a laptop
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
    from PIL import Image

    root, out = args.dir, args.out
    key, parent = read_key(root), None
    parent = parents(root, key)
    crops = args.crops or (root / "crops")

    done = {}
    if out.exists():   # Colab kills idle sessions; don't lose 20 minutes to one.
        done = {r["crop_id"]: r for r in csv.DictReader(out.open())}
        print(f"resuming: {len(done)} already predicted")
    todo = [c for c in sorted(key) if c not in done]
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
            print(f"  crop 1: file {img.size[0]}x{img.size[1]} -> model sees "
                  f"{ww * 14}x{h * 14} px  (floor {int(MIN_PIXELS ** .5)}²)")

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
    assert parse_answer("a blue rectangle", "Warning") == "unparsed"
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
    s.set_defaults(fn=fn)
args = ap.parse_args()
args.fn(args)
