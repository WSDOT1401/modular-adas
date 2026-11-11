"""Draw fake Thai speed-limit signs, then wreck them until they look like dashcam frames.

We have ~28 unique real signs -- far too few to train 2.5M parameters. But a speed
limit sign is a *drawn standard*, so we can render unlimited perfect ones and then
degrade them to match our footage. The degradation is the part that matters: a clean
256px render teaches the model nothing about a blurry 35px sign on a wet morning.

Every variation below was copied off real crops in sheet.png -- yellow and orange
roadworks plates, red digits (#4), "Km/h" subtext (#3), sun-bleached rings (#23/#24).

    python synth.py        # -> synth_sheet.png, eyeball it next to sheet.png
"""
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# Thai standard values.  70/100/110 never appear in our footage but do appear on the
# road, so the model must know them -- we just cannot measure them.
VALUES = [20, 30, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120]

FONTS = [("/System/Library/Fonts/Helvetica.ttc", 1),
         ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
         ("/System/Library/Fonts/Supplemental/Arial Narrow.ttf", 0),
         ("/System/Library/Fonts/Avenir Next Condensed.ttc", 0),
         ("/System/Library/Fonts/Supplemental/Tahoma Bold.ttf", 0),
         ("/System/Library/Fonts/Supplemental/Verdana Bold.ttf", 0)]

# The sign FACE is always white-ish. The yellow and orange in our footage (#25, #26,
# #35, #38) is a rectangular BACKING BOARD behind the sign, not the sign face -- look
# at real/025.png. Modelling it as a coloured face was simply wrong, and those crops
# were among the ones we got wrong.
FACES = [(255, 255, 255)] * 9 + [(252, 246, 215)]          # white, occasionally yellowed
BOARDS = [(255, 255, 255), (250, 240, 90), (245, 160, 40), (225, 225, 220)]
R = 256                                                                     # render size

_BG_CACHE = []


def backgrounds(dataset=None, n=120):
    """Random tiles from our own footage -- the only in-domain backgrounds we have,
    and they cost nothing because they are already on disk."""
    if _BG_CACHE:
        return _BG_CACHE
    dataset = dataset or Path(__file__).resolve().parents[1] / "thai-traffic-sign-labs/autolabel/dataset"
    frames = sorted(dataset.glob("images/*/*.jpg"))
    for p in random.sample(frames, min(n, len(frames))):
        im = Image.open(p)
        im.draft("RGB", (im.width // 4, im.height // 4))    # JPEG fast-path: decode small
        _BG_CACHE.append(im.convert("RGB"))
    return _BG_CACHE


def _fit(draw, text, font_path, idx, target_h, max_w=None):
    """Binary-search a point size so the digits are target_h tall AND at most max_w
    wide. Fonts disagree wildly about what 'size' means, so measuring beats guessing.

    The width bound is not cosmetic. Without it "120" renders wider than the white
    field and spills over the red ring -- which no real sign does -- and the model
    learns "wide dark blob = 3 digits", then reads every blurry 2-digit sign as 120.
    """
    lo, hi = 4, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        f = ImageFont.truetype(font_path, mid, index=idx)
        box = draw.textbbox((0, 0), text, font=f)
        if (box[3] - box[1]) <= target_h and (max_w is None or (box[2] - box[0]) <= max_w):
            lo = mid
        else:
            hi = mid - 1
    return ImageFont.truetype(font_path, lo, index=idx)


def render(value=None, rng=random):
    """One clean sign on transparent background. Returns (RGBA image, value)."""
    value = value if value is not None else rng.choice(VALUES)
    im = Image.new("RGBA", (R, R), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # Roughly half our signs sit on a rectangular board; the circle is then smaller
    # relative to the detector crop, which is exactly what real/026.png looks like.
    if rng.random() < 0.45:
        k = rng.uniform(0.70, 1.0)
        board = tuple(int(c * k) for c in rng.choice(BOARDS))
        d.rectangle([0, 0, R - 1, R - 1], fill=board)
        inset = rng.uniform(0.06, 0.17) * R
    else:
        inset = 0.0
    lo, hi = inset, R - 1 - inset
    dia = hi - lo

    ring_w = rng.uniform(0.065, 0.105) * dia      # measured off real crops: thinner than it looks
    fade = rng.uniform(0.0, 0.45)                 # sun-bleached rings: #23, #24, #44
    red = tuple(int(c + (255 - c) * fade) for c in (200, 25, 35))
    k = rng.uniform(0.72, 1.0)                 # ONE factor for all 3 channels; per-channel
    plate = tuple(int(c * k) for c in rng.choice(FACES))   # would tint the face blue/purple

    d.ellipse([lo, lo, hi, hi], fill=red)
    d.ellipse([lo + ring_w, lo + ring_w, hi - ring_w, hi - ring_w], fill=plate)

    text = str(value)
    digit_c = (190, 20, 25) if rng.random() < 0.06 else (25, 25, 25)   # red digits: #4
    sub = rng.random() < 0.10                                          # "Km/h" subtext: #3
    h = rng.uniform(0.38, 0.48) * dia          # real signs leave more white than I first drew
    # widest the white field is at digit height -- a circle, so it narrows as h grows
    r_in = dia / 2 - ring_w
    max_w = 2 * max(1.0, r_in**2 - (h / 2) ** 2) ** 0.5 * rng.uniform(0.70, 0.86)
    font_path, idx = rng.choice(FONTS)
    f = _fit(d, text, font_path, idx, h, max_w)

    box = d.textbbox((0, 0), text, font=f)
    cx = cy0 = (lo + hi) / 2
    cy = cy0 - (h * 0.22 if sub else 0)
    d.text((cx - (box[2] + box[0]) / 2, cy - (box[3] + box[1]) / 2), text, font=f, fill=digit_c)
    if sub:
        sf = _fit(d, "Km/h", font_path, idx, h * 0.30, max_w * 0.8)
        sb = d.textbbox((0, 0), "Km/h", font=sf)
        d.text((cx - (sb[2] + sb[0]) / 2, cy + h * 0.45), "Km/h", font=sf, fill=digit_c)
    return im, value


def degrade(sign, rng=random, out=64, px=None):
    """Clean 256px render -> something that looks like it came off the dashcam.

    Order matters: it mirrors the real pipeline. Skew and light happen in the world,
    THEN the camera shrinks and blurs and JPEGs it. Blurring after downscaling would
    produce a smooth small image, which is not what a real 35px crop looks like.
    """
    # -- in the world: signs are seen off-axis and slightly rotated on the pole
    j = R * rng.uniform(0.0, 0.16)
    quad = [c + rng.uniform(-j, j) for c in (0, 0, 0, R, R, R, R, 0)]
    sign = sign.rotate(rng.uniform(-7, 7), Image.BILINEAR, expand=False)
    sign = sign.transform((R, R), Image.QUAD, quad, Image.BILINEAR)

    bgs = backgrounds()
    bg = rng.choice(bgs)
    x, y = rng.randint(0, bg.width - 80), rng.randint(0, bg.height - 80)
    s = rng.randint(60, min(bg.width - x, bg.height - y))
    canvas = bg.crop((x, y, x + s, y + s)).resize((R, R), Image.BILINEAR)

    pad = int(R * rng.uniform(0.0, 0.14))                 # detector boxes are loose
    sz = R - 2 * pad
    ox = pad + rng.randint(-pad, pad) if pad else 0       # ...and rarely dead-centre
    oy = pad + rng.randint(-pad, pad) if pad else 0
    sized = sign.resize((sz, sz), Image.LANCZOS)
    canvas.paste(sized, (ox, oy), sized)

    # -- light: dusk, glare, overcast, white balance drift
    canvas = ImageEnhance.Brightness(canvas).enhance(rng.uniform(0.45, 1.45))
    canvas = ImageEnhance.Contrast(canvas).enhance(rng.uniform(0.55, 1.35))
    canvas = ImageEnhance.Color(canvas).enhance(rng.uniform(0.35, 1.30))

    # -- the camera: shrink to a real-world crop size, then smear and compress
    px = px or int(round(rng.lognormvariate(3.85, 0.40)))  # median ~47px, tail down to the 32px gate
    px = max(26, min(150, px))
    small = canvas.resize((px, px), Image.BILINEAR)
    if rng.random() < 0.55:
        small = small.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.1)))
    if rng.random() < 0.30:                                # horizontal smear from driving past
        k = [0] * 5 + [0.2] * 5 + [0] * 15
        small = small.filter(ImageFilter.Kernel((5, 5), k, scale=1.0))
    if rng.random() < 0.7:
        import io
        b = io.BytesIO()
        small.save(b, "JPEG", quality=rng.randint(18, 75))
        small = Image.open(b).convert("RGB")
    return small.resize((out, out), Image.BILINEAR)


def sample(rng=random, out=64):
    sign, value = render(rng=rng)
    return degrade(sign, rng=rng, out=out), value


def main():
    """Self-check: 56 samples at display size. Compare against sheet.png -- if these
    do not look like those, training on them is pointless."""
    random.seed(0)
    cols, cell = 7, 128
    sh = Image.new("RGB", (cols * cell, 8 * (cell + 14)), "white")
    d = ImageDraw.Draw(sh)
    for i in range(56):
        img, v = sample()
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        sh.paste(img.resize((cell, cell), Image.NEAREST), (x, y))
        d.text((x + 2, y + cell + 1), f"{v}", fill="black")
    sh.save(Path(__file__).parent / "synth_sheet.png")
    assert len(VALUES) == 12
    print("wrote synth_sheet.png -- compare it against sheet.png")


if __name__ == "__main__":
    main()
