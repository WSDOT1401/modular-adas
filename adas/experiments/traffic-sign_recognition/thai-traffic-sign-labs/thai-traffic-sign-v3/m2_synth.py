#!/usr/bin/env python3
"""Infinite synthetic crops for the 12 pictogram classes M2 displays.

Same trick as speed_limit_classifier, which trained on synth only and scored
86.8% on real footage: a regulatory sign is a *drawn standard*, so we can render
unlimited perfect ones and wreck them until they look like our dashcam. All the
wrecking is synth.degrade() -- unmodified, because it already takes a 256px RGBA
and uses the alpha channel as its paste mask.

Nothing is written to disk. Every call draws a fresh sign, so there is no fixed
synthetic set for the model to memorise; `n` in the training loop is just how
long an epoch is.

    python m2_synth.py        # -> m2_synth_sheet.png, eyeball it against real crops

Not here: `information` (a family of boards with arbitrary content, not one
drawing -- and it has 357 real crops), and the 15 helper classes, which exist
only to keep the dash quiet and already have real crops.
"""
import functools
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ART = HERE / "art"
DATASET = HERE.parent / "autolabel" / "dataset"

sys.path.insert(0, str(HERE.parents[1] / "speed_limit_classifier"))
sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402
import synth  # noqa: E402

SIZE = 128    # NOT 64. MobileNetV3-Small downsamples 32x, so a 64px input leaves
              # a 2x2 final feature map and the net cannot tell a 6 from an 8.
              # Measured in speed_limit_classifier: 64 -> 128 took real accuracy
              # 72.2% -> 91.7%. See its train.py.

# class -> its drawings. Three classes are two drawings each (b-38 straight vs
# b-43 bent, and so on); picking one at sample time means the model sees both.
VARIANTS = {}
for p in sorted(ART.glob("*__*.png")):
    VARIANTS.setdefault(p.name.split("__")[0], []).append(p)

CLASSES = sorted(VARIANTS) + ["speed_limit"]   # speed_limit is drawn, not downloaded


@functools.lru_cache(maxsize=None)
def _art(path):
    """degrade() never mutates what it is handed, so one load serves every sample."""
    return Image.open(path).convert("RGBA")


def _train_backgrounds(n=120):
    """Seed synth.py's background cache from TRAIN frames only.

    synth.backgrounds() globs images/*/*.jpg, which includes val. The tiles are
    only texture behind the sign, but a val frame inside a training sample is
    still a val frame inside a training sample.
    """
    if synth._BG_CACHE:
        return
    frames = sorted((DATASET / "images" / "train").glob("*.jpg"))
    assert frames, f"no training frames under {DATASET} -- run prelabel.py build"
    for p in random.sample(frames, min(n, len(frames))):
        im = Image.open(p)
        im.draft("RGB", (im.width // 4, im.height // 4))    # JPEG fast path
        synth._BG_CACHE.append(im.convert("RGB"))


def sample(name=None, rng=random, out=SIZE):
    """One degraded crop. Returns (RGB image, class name)."""
    _train_backgrounds()
    name = name or rng.choice(CLASSES)
    if name == "speed_limit":
        sign, _value = synth.render(rng=rng)   # the drawn variants, not the SVG
    else:
        sign = _art(rng.choice(VARIANTS[name]))
    return synth.degrade(sign, rng=rng, out=out), name


def main():
    """Self-check: 4 samples of every class. If these do not look like the real
    crops in the dataset, training on them is pointless."""
    random.seed(0)
    cols, cell = 4, 112
    sh = Image.new("RGB", (cols * cell, len(CLASSES) * (cell + 14)), "white")
    d = ImageDraw.Draw(sh)
    for row, name in enumerate(CLASSES):
        for col in range(cols):
            img, got = sample(name)
            assert got == name and img.size == (SIZE, SIZE)
            x, y = col * cell, row * (cell + 14)
            sh.paste(img.resize((cell, cell), Image.NEAREST), (x, y))
        d.text((2, row * (cell + 14) + cell + 1), name, fill="black")
    sh.save(HERE / "m2_synth_sheet.png")
    # The contract: every class the dash shows is synthesisable, except the one
    # that is a family of text boards rather than a drawing.
    assert set(CLASSES) == set(classes.THAI_FINE_DISPLAYED) - {"information"}, CLASSES
    print(f"{len(CLASSES)} classes, {sum(map(len, VARIANTS.values()))} drawings"
          f" -> m2_synth_sheet.png")


if __name__ == "__main__":
    main()
