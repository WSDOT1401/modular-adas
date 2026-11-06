"""One-shot: pull every speed_limit box out of the YOLO dataset into real/.

These 60 crops are the TEST SET. We never train on them -- the model learns from
synth.py and is judged here, on real footage it has never seen.

    python crops.py            # -> real/*.png, labels.csv, sheet.png
"""
import csv
import sys
from pathlib import Path
from PIL import Image, ImageDraw

DATASET = Path(__file__).resolve().parents[1] / "thai-traffic-sign-labs/autolabel/dataset"
SPEED_LIMIT = 5          # class index in data.yaml
MARGIN = 0.10            # detector boxes are not pixel-perfect; mimic that slack
OUT = Path(__file__).parent


def square_box(cx, cy, w, h, iw, ih):
    """Tight YOLO box -> square crop box, so the round sign stays round at 64x64."""
    side = max(w, h) * (1 + 2 * MARGIN)
    half = side / 2
    return (max(0, cx - half), max(0, cy - half),
            min(iw, cx + half), min(ih, cy + half))


def extract():
    rows = []
    for lbl in sorted(DATASET.glob("labels/*/*.txt")):
        img_path = next((p for p in
                         [Path(str(lbl).replace("/labels/", "/images/")).with_suffix(ext)
                          for ext in (".jpg", ".png", ".jpeg")] if p.exists()), None)
        if img_path is None:
            continue
        for line in lbl.read_text().splitlines():
            parts = line.split()
            if not parts or int(parts[0]) != SPEED_LIMIT:
                continue
            im = Image.open(img_path).convert("RGB")
            xc, yc, bw, bh = (float(v) for v in parts[1:5])
            box = square_box(xc * im.width, yc * im.height,
                             bw * im.width, bh * im.height, im.width, im.height)
            rows.append((lbl.stem, round(bw * im.width), im.crop(box)))
    rows.sort(key=lambda r: -r[1])           # biggest (most readable) first
    return rows


def main():
    if (OUT / "labels.csv").exists() and "--force" not in sys.argv:
        sys.exit("labels.csv already exists and holds hand-read labels.\n"
                 "Re-running renumbers every crop and throws them away. Use --force if you mean it.")
    (OUT / "real").mkdir(exist_ok=True)
    rows = extract()
    with open(OUT / "labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "file", "px", "source", "label"])
        for i, (stem, px, crop) in enumerate(rows):
            name = f"{i:03d}.png"
            crop.save(OUT / "real" / name)
            w.writerow([i, name, px, stem, ""])   # label filled in by eye
    sheet(rows)
    print(f"{len(rows)} crops -> real/  ({sum(px >= 32 for _, px, _ in rows)} are >=32px)")
    print("now fill the 'label' column in labels.csv by reading sheet.png")


def sheet(rows, cols=7, cell=128):
    """Contact sheet so a human can read the numbers and fill in labels.csv."""
    n_rows = (len(rows) + cols - 1) // cols
    sh = Image.new("RGB", (cols * cell, n_rows * (cell + 14)), "white")
    d = ImageDraw.Draw(sh)
    for i, (stem, px, crop) in enumerate(rows):
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        sh.paste(crop.resize((cell, cell), Image.LANCZOS), (x, y))
        d.text((x + 2, y + cell + 1), f"#{i} {px}px", fill="black")
    sh.save(OUT / "sheet.png")


if __name__ == "__main__":
    main()
