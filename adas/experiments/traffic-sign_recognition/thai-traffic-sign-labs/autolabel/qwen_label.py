#!/usr/bin/env python3
"""Name every crop in a batch with Qwen2.5-VL. Runs on Colab; needs a GPU.

    python qwen_label.py --crops crops --map source_map.csv --out predictions.csv

This is the ``run`` half of the golden experiment's ``classify.py``, with the
answer-key and scoring machinery removed -- in this pipeline every crop is
unlabelled, so there is nothing to grade against. The prompt is byte-identical
to the v3 prompt that produced the measured numbers in
``golden-experiment/RESULTS.md``; do not reword it without re-measuring.

The detector already decided each crop's coarse class, so the question put to
the model is ~13-way (Regulatory) or ~6-way (Warning), never 21-way.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys

# On Colab classes.py rides along in crops.zip next to this file; in the repo it
# lives two levels up. Try alongside first so the Colab copy always wins.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE if (_HERE / "classes.py").exists() else _HERE.parents[1]))
import classes  # noqa: E402

MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
ABSTAIN = "unclear"

# Qwen2.5-VL picks its own input resolution and the default SHRINKS a 448px
# crop. For a sign whose whole identity is a small glyph that is fatal, and it
# fails silently -- you just get bad numbers. Floor it at the crop's own size.
MIN_PIXELS, MAX_PIXELS = 448 * 448, 896 * 896

# Written from the crops themselves, not from any error list -- describing only
# the classes that failed would be tuning the prompt against the test set.
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


def catch_all(parent: str) -> str:
    """Regulatory and Warning have an explicit ``other_*``; Information does not
    -- ``information`` itself is the catch-all. Building this name mechanically
    as ``"other_" + parent.lower()`` offered Qwen a class that does not exist and
    silently scored 80 refusals as confident answers."""
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
    # The closing rule targets the dominant early failure: Qwen almost never
    # picked a catch-all, preferring to name the nearest specific sign. Naming
    # the behaviour is the fix; listing the option was not enough.
    art = "an" if parent[0] in "AEIOU" else "a"
    return (f"This photo is a Thai road sign, already known to be {art} {parent} sign.\n\n"
            "Which sign is it? Reply with exactly one name from this list and "
            "nothing else:\n\n" + "\n".join(lines) +
            f"\n\nRule: if the sign does not match one of the descriptions above, "
            f"answer {other}. Do not pick the closest match — a sign that merely "
            f"resembles an option, without matching its description, is {other}.")


def parse_answer(raw: str, parent: str) -> str:
    """Longest option name present in the reply, else 'unparsed'.

    Longest-first matters: 'no_right_u_turn' contains 'no_right_turn' and
    'keep_left_or_right' contains 'keep_left'. Word boundaries matter too:
    'other_information' contains 'information', and a bare substring test
    silently scored 80 refusals as confident answers.
    """
    low = raw.lower()
    for o in sorted(classes.THAI_FINE_BY_PARENT[parent] + (ABSTAIN,), key=len, reverse=True):
        if re.search(rf"\b{re.escape(o)}\b", low):
            return o
    return "unparsed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", type=pathlib.Path, default=pathlib.Path("crops"))
    ap.add_argument("--map", type=pathlib.Path, default=pathlib.Path("source_map.csv"))
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("predictions.csv"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    if a.selfcheck:
        assert catch_all("Information") == "information"
        assert catch_all("Regulatory") == "other_regulatory"
        assert "other_information" not in prompt_for("Information")
        # "other_information" is not a class. A bare substring test matched
        # "information" inside it and scored 80 refusals as confident answers;
        # the word-boundary search must return unparsed instead.
        assert parse_answer("other_information", "Information") == "unparsed"
        assert parse_answer("the answer is no_right_u_turn", "Regulatory") == "no_right_u_turn"
        assert parse_answer("keep_left_or_right", "Regulatory") == "keep_left_or_right"
        assert parse_answer("nonsense", "Warning") == "unparsed"
        print("ok")
        return

    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
    from PIL import Image

    parent = {r["crop_id"]: r["coarse"] for r in csv.DictReader(a.map.open())}
    want = sorted(parent)

    done = {}
    if a.out.exists():   # Colab kills idle sessions; don't lose 20 minutes to one.
        done = {r["crop_id"] for r in csv.DictReader(a.out.open())}
        print(f"resuming: {len(done)} already predicted")
    todo = [c for c in want if c not in done][:a.limit or None]
    if not todo:
        sys.exit(f"nothing to do — {a.out} already covers every crop")

    print(f"loading {a.model} in 4-bit …")
    proc = AutoProcessor.from_pretrained(a.model, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
    model = AutoModelForImageTextToText.from_pretrained(
        a.model, device_map="auto",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            # fp16, not bf16: the free Colab T4 is Turing and has no bf16 units.
            bnb_4bit_compute_dtype=torch.float16))
    model.eval()

    fh = a.out.open("a" if done else "w", newline="")
    w = csv.writer(fh)
    if not done:
        w.writerow(["crop_id", "parent", "pred", "raw"])

    for i, crop in enumerate(todo, 1):
        img = Image.open(a.crops / f"{crop}.jpg").convert("RGB")
        msgs = [{"role": "user", "content": [
            {"type": "image"}, {"type": "text", "text": prompt_for(parent[crop])}]}]
        text = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        inputs = proc(text=[text], images=[img], return_tensors="pt").to(model.device)

        if i == 1:   # prove the resize floor took effect before burning 25 min
            h, ww = inputs["image_grid_thw"][0][1:].tolist()
            seen, have = ww * 14 * h * 14, img.size[0] * img.size[1]
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
    print(f"\nwrote {a.out} — download it, then on your laptop:\n"
          f"  prelabel.py from-colab <batch> ~/Downloads/{a.out.name}")


if __name__ == "__main__":
    main()
