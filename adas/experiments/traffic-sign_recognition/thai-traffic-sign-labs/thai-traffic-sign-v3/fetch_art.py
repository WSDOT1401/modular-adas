#!/usr/bin/env python3
"""Download the official Thai sign artwork that M2 synthesises from.

Wikimedia Commons holds every pictogram we need as SVG, Public domain, author
"Government of Thailand", and renders SVG->PNG server-side -- so this needs no
rasteriser, just urllib. Run it once; art/ is committed, so a build never needs
the network.

    python fetch_art.py          # -> art/<class>__<code>.png, 256 px RGBA

Three classes are two drawings each. `turn_left` is both the straight arrow
(b-38) and the bent one (b-43); `turn_right` likewise; `stop` is Thai-only and
bilingual. Synthesise one variant and the model learns half the class, so both
are downloaded and m2_synth.py picks between them at sample time.

`speed_limit` is deliberately absent. The SVG b-32 is an idealised sign, while
speed_limit_classifier/synth.py draws the variants copied off our own crops --
yellow and orange backing boards, sun-bleached rings, "Km/h" subtext, red
digits -- and scored 86.8% on real footage. Do not swap tested code for
cleaner artwork.
"""
import json
import pathlib
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ART = HERE / "art"
PX = 256          # degrade() takes a 256px RGBA; see m2_synth.py
API = "https://commons.wikimedia.org/w/api.php"

# <output name> -> Thai sign code. The code is kept in the filename because the
# first question in the room will be "where did these come from".
SIGNS = {
    "stop__b-1":               "บ-1",
    "stop__b-1-1":             "บ-1-1",
    "no_left_turn__b-8":       "บ-8",
    "no_right_turn__b-9":      "บ-9",
    "no_right_u_turn__b-6":    "บ-6",
    "keep_left__b-40":         "บ-40",
    "keep_right__b-41":        "บ-41",
    "keep_left_or_right__b-42": "บ-42",
    "turn_left__b-38":         "บ-38",
    "turn_left__b-43":         "บ-43",
    "turn_right__b-39":        "บ-39",
    "turn_right__b-44":        "บ-44",
    "left_curve__t-1":         "ต-1",
    "left_curve__t-3":         "ต-3",      # the sharp-bend drawing, also in our footage
    "right_curve__t-2":        "ต-2",
    "right_curve__t-4":        "ต-4",
    "stop__b-1-2":             "บ-1-2",    # octagon, English only
    # 14 of our 22 keep_left_or_right crops are this yellow diamond ("obstacle,
    # pass either side"), not the blue circle. Synthesising only b-42 would
    # teach two thirds of the class as the wrong drawing.
    "keep_left_or_right__t-62": "ต-62",
}

# The sign our footage actually shows for "turn left/right ahead": white disc,
# RED ring, black bent arrow, no bar. Commons has no code for it -- it predates
# the blue b-38/b-43, which does not appear once in our clips -- but b-8/b-9
# ("no left/right turn") carry the identical arrow glyph under a prohibition
# bar. Delete the bar and the drawing is right. Checked at 100 px in the
# footage: the real signs have no bar, and the ones that do are labelled
# no_left_turn/no_right_turn, which the model still has to tell apart.
DERIVED = {"turn_left__red-ring": "บ-8", "turn_right__red-ring": "บ-9"}
RING = 0.85   # measured on b-8: the ring is >=74% of every annulus from here
              # out and the bar is <=30% inside it, so the cut is not a
              # judgement call. See JOURNAL 2026-11-16.


def strip_bar(im):
    """b-8/b-9 minus the prohibition bar."""
    a = np.array(im)
    r, g, b = (a[..., i].astype(int) for i in range(3))
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.hypot(yy - (h - 1) / 2, xx - (w - 1) / 2) < RING * min(h, w) / 2
    a[inside & (r - np.maximum(g, b) > 25)] = (255, 255, 255, 255)
    return Image.fromarray(a)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "thai-sign-dataset/1.0"})
    return urllib.request.urlopen(req).read()


def main():
    ART.mkdir(exist_ok=True)
    q = {"action": "query", "format": "json", "prop": "imageinfo",
         "iiprop": "url", "iiurlwidth": str(PX),
         "titles": "|".join(f"File:Thailand road sign {c}.svg"
                            for c in {**SIGNS, **DERIVED}.values())}
    pages = json.loads(get(API + "?" + urllib.parse.urlencode(q)))["query"]["pages"]
    thumb = {p["title"]: p["imageinfo"][0]["thumburl"]
             for p in pages.values() if "imageinfo" in p}

    for name, code in {**SIGNS, **DERIVED}.items():
        url = thumb.get(f"File:Thailand road sign {code}.svg")
        assert url, f"{code} is not on Commons under that title any more"
        out = ART / f"{name}.png"
        out.write_bytes(get(url))

        # The two curve diamonds come back palette-mode. Without the convert
        # they paste as opaque yellow SQUARES and the model learns "yellow
        # square = curve" -- which is also what a chevron looks like at 30 px.
        im = Image.open(out).convert("RGBA")
        assert im.getchannel("A").getextrema()[0] == 0, f"{name}: no transparency"
        if name in DERIVED:
            im = strip_bar(im)
        im.thumbnail((PX, PX), Image.LANCZOS)
        square = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))   # degrade() wants PXxPX
        square.paste(im, ((PX - im.width) // 2, (PX - im.height) // 2))
        square.save(out)
        print(f"  {name:28s} {code}{'  (bar removed)' if name in DERIVED else ''}")
    print(f"{len(SIGNS) + len(DERIVED)} drawings -> {ART}")


if __name__ == "__main__":
    main()
