#!/usr/bin/env python3
"""Dataset fitness audit for thai-traffic-sign-labs. Reads from disk only."""
import csv, json, os, re, sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ExifTags

ROOT = Path(__file__).resolve().parent.parent / "datasets"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
IMGSZ = 1024

def hdr(t): print(f"\n{'='*70}\n{t}\n{'='*70}")

# ---------- 1. structure ----------
hdr("1. STRUCTURE")
coco_img_dir = ROOT / "COCO/images"
y_img_dir = ROOT / "YOLO/images/train"
y_lbl_dir = ROOT / "YOLO/labels/train"

def stems(d, exts):
    return {p.stem: p for p in d.iterdir() if p.suffix.lower() in exts and not p.name.startswith('.')}

coco_imgs = stems(coco_img_dir, {".jpg", ".jpeg", ".png"})
y_imgs = stems(y_img_dir, {".jpg", ".jpeg", ".png"})
y_lbls = stems(y_lbl_dir, {".txt"})
print(f"COCO/images        : {len(coco_imgs)}")
print(f"YOLO/images/train  : {len(y_imgs)}")
print(f"YOLO/labels/train  : {len(y_lbls)}")
print(f"img w/o label      : {sorted(set(y_imgs)-set(y_lbls))[:10]}  (n={len(set(y_imgs)-set(y_lbls))})")
print(f"label w/o img      : {sorted(set(y_lbls)-set(y_imgs))[:10]}  (n={len(set(y_lbls)-set(y_imgs))})")
print(f"COCO-only imgs     : {sorted(set(coco_imgs)-set(y_imgs))[:10]}  (n={len(set(coco_imgs)-set(y_imgs))})")

# are YOLO and COCO images the same bytes or copies?
import hashlib
def md5(p, n=1<<20):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        while (b := f.read(n)): h.update(b)
    return h.hexdigest()
common = sorted(set(coco_imgs) & set(y_imgs))[:20]
same = sum(md5(coco_imgs[s]) == md5(y_imgs[s]) for s in common)
print(f"COCO vs YOLO image bytes identical: {same}/{len(common)} sampled")

# train.txt
tt = ROOT / "YOLO/train.txt"
tt_lines = [l.strip() for l in tt.read_text().splitlines() if l.strip()]
tt_stems = {Path(l).stem for l in tt_lines}
tt_missing = [l for l in tt_lines if not (ROOT / "YOLO" / l).exists()]
print(f"train.txt entries  : {len(tt_lines)}  dupes={len(tt_lines)-len(tt_stems)}  missing-on-disk={len(tt_missing)}")
print(f"train.txt == images dir: {tt_stems == set(y_imgs)}")

yaml = (ROOT / "YOLO/data.yaml").read_text()
print(f"data.yaml declares splits: {[k for k in ('train','val','test') if re.search(rf'^{k}\s*:', yaml, re.M)]}")

# ---------- 2/3. labels + boxes ----------
hdr("2+3. LABELS & BOXES")
coco = json.loads((ROOT / "COCO/annotations/instances_default.json").read_text())
cat_by_id = {c["id"]: c["name"] for c in coco["categories"]}
NAMES = {0: "Regulatory", 1: "Warning", 2: "Information"}

malformed, boxes = [], []   # boxes: dict rows
empty_labels = []
for stem in sorted(y_lbls):
    txt = y_lbls[stem].read_text()
    lines = [l for l in txt.splitlines() if l.strip()]
    if not lines:
        empty_labels.append(stem); continue
    for i, l in enumerate(lines):
        p = l.split()
        if len(p) != 5:
            malformed.append((stem, i, "field-count", l)); continue
        try:
            c = int(p[0]); x, y, w, h = map(float, p[1:])
        except ValueError:
            malformed.append((stem, i, "parse", l)); continue
        boxes.append(dict(stem=stem, cls=c, xc=x, yc=y, w=w, h=h))
print(f"label files        : {len(y_lbls)}   empty (background): {len(empty_labels)}")
print(f"malformed lines    : {len(malformed)}  {malformed[:5]}")
print(f"YOLO box rows      : {len(boxes)}   COCO annotations: {len(coco['annotations'])}")

cls_counts = Counter(b["cls"] for b in boxes)
coco_counts = Counter(cat_by_id[a["category_id"]] for a in coco["annotations"])
print(f"\nundeclared class ids (not in data.yaml): {sorted(set(cls_counts) - set(NAMES))}")
print(f"declared-but-unused ids               : {sorted(set(NAMES) - set(cls_counts))}")

boxes_per_img = Counter()
for b in boxes: boxes_per_img[b["stem"]] += 1
for s in empty_labels: boxes_per_img[s] = 0
bpi = np.array([boxes_per_img[s] for s in y_lbls])
print(f"\nboxes/image: mean={bpi.mean():.2f} median={np.median(bpi):.0f} max={bpi.max()} "
      f"| imgs with 0={int((bpi==0).sum())} 1={int((bpi==1).sum())} 2={int((bpi==2).sum())} 3+={int((bpi>=3).sum())}")

# ---------- 4. images ----------
hdr("4. IMAGES")
coco_dims = {im["file_name"]: (im["width"], im["height"]) for im in coco["images"]}
img_rows, corrupt, exif_rot, dim_mismatch = [], [], [], []
ORIENT_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
hashes = {}
for stem in sorted(y_imgs):
    p = y_imgs[stem]
    try:
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            W, H = im.size
            ex = im.getexif()
            o = ex.get(ORIENT_TAG, 1) if ex else 1
            g = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    except Exception as e:
        corrupt.append((stem, repr(e))); continue
    if o not in (1, 0, None): exif_rot.append((stem, o))
    cw, ch = coco_dims.get(p.name, (None, None))
    if cw and (cw, ch) != (W, H): dim_mismatch.append((stem, (W, H), (cw, ch)))
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    hashes[stem] = np.packbits(bits)
    img_rows.append(dict(stem=stem, w=W, h=H, bytes=p.stat().st_size, exif_orient=o,
                         n_boxes=boxes_per_img[stem]))
print(f"unreadable/corrupt : {len(corrupt)} {corrupt[:3]}")
print(f"EXIF orientation !=1: {len(exif_rot)} {exif_rot[:5]}")
print(f"size mismatch COCO vs file: {len(dim_mismatch)} {dim_mismatch[:3]}")
res = Counter((r["w"], r["h"]) for r in img_rows)
print(f"resolutions        : {dict(res)}")

# near-duplicate frames via dHash hamming distance
stems_l = [r["stem"] for r in img_rows]
Hm = np.stack([np.unpackbits(hashes[s]) for s in stems_l])
D = (Hm[:, None, :] != Hm[None, :, :]).sum(-1)
iu = np.triu_indices(len(stems_l), 1)
dup_pairs = [(stems_l[i], stems_l[j], int(D[i, j])) for i, j in zip(*iu) if D[i, j] <= 10]
print(f"near-dup pairs (dHash<=10): {len(dup_pairs)}  (<=5: {sum(1 for *_ ,d in dup_pairs if d<=5)})")

# clip grouping from filename  YYYY_MMDD_HHMMSS_fNNNNNN
clip_re = re.compile(r"^(.*)_f(\d+)$")
clips = defaultdict(list)
for s in stems_l:
    m = clip_re.match(s)
    clips[m.group(1) if m else "UNPARSED"].append(int(m.group(2)) if m else -1)
print(f"source clips       : {len(clips)}  frames/clip: "
      f"min={min(len(v) for v in clips.values())} max={max(len(v) for v in clips.values())} "
      f"median={int(np.median([len(v) for v in clips.values()]))}")
# frame stride within clip
strides = []
for k, v in clips.items():
    v = sorted(v)
    strides += [b - a for a, b in zip(v, v[1:])]
if strides:
    print(f"frame-index gaps   : median={int(np.median(strides))} min={min(strides)} max={max(strides)}")

# ---------- box geometry (needs dims) ----------
hdr("3b. BOX GEOMETRY")
dims = {r["stem"]: (r["w"], r["h"]) for r in img_rows}
bad_range, zero_area, clipped = [], [], []
for b in boxes:
    W, H = dims.get(b["stem"], (None, None))
    if W is None: continue
    b["W"], b["H"] = W, H
    b["pw"], b["ph"] = b["w"] * W, b["h"] * H
    b["area_n"] = b["w"] * b["h"]
    b["ar"] = b["pw"] / b["ph"] if b["ph"] else float("inf")
    s = IMGSZ / max(W, H)                     # YOLO letterbox scale
    b["pw_i"], b["ph_i"] = b["pw"] * s, b["ph"] * s
    b["side_i"] = (b["pw_i"] * b["ph_i"]) ** 0.5
    x1, y1 = b["xc"] - b["w"] / 2, b["yc"] - b["h"] / 2
    x2, y2 = b["xc"] + b["w"] / 2, b["yc"] + b["h"] / 2
    b["x1"], b["y1"], b["x2"], b["y2"] = x1, y1, x2, y2
    if b["w"] <= 0 or b["h"] <= 0: zero_area.append(b)
    if not (0 <= b["xc"] <= 1 and 0 <= b["yc"] <= 1) or b["w"] > 1 or b["h"] > 1: bad_range.append(b)
    if x1 < -1e-6 or y1 < -1e-6 or x2 > 1 + 1e-6 or y2 > 1 + 1e-6: clipped.append(b)
print(f"zero/negative area : {len(zero_area)}")
print(f"out-of-range norm  : {len(bad_range)}")
print(f"touching/over edge : {len(clipped)}  {[(b['stem'],round(b['x1'],3),round(b['y1'],3),round(b['x2'],3),round(b['y2'],3)) for b in clipped[:5]]}")

def q(a, name, unit=""):
    a = np.asarray(a)
    print(f"{name:<22} min={a.min():8.2f} p05={np.percentile(a,5):8.2f} p25={np.percentile(a,25):8.2f} "
          f"med={np.median(a):8.2f} p75={np.percentile(a,75):8.2f} p95={np.percentile(a,95):8.2f} max={a.max():8.2f} {unit}")

print()
q([b["pw"] for b in boxes], "native box width", "px")
q([b["ph"] for b in boxes], "native box height", "px")
q([(b["pw"]*b["ph"])**0.5 for b in boxes], "native sqrt(area)", "px")
q([b["area_n"]*100 for b in boxes], "norm area", "% of image")
q([b["ar"] for b in boxes], "aspect ratio w/h")
q([b["side_i"] for b in boxes], f"sqrt(area) @{IMGSZ}", "px")
q([b["yc"] for b in boxes], "box center y (norm)")
q([b["xc"] for b in boxes], "box center x (norm)")

side_i = np.array([b["side_i"] for b in boxes])
print(f"\n@imgsz {IMGSZ}: <8px={int((side_i<8).sum())} ({100*(side_i<8).mean():.1f}%)  "
      f"<12px={int((side_i<12).sum())} ({100*(side_i<12).mean():.1f}%)  "
      f"<16px={int((side_i<16).sum())} ({100*(side_i<16).mean():.1f}%)  "
      f"<32px={int((side_i<32).sum())} ({100*(side_i<32).mean():.1f}%)")
print(f"COCO-scale small(<32px @native)={int(sum(1 for b in boxes if (b['pw']*b['ph'])**0.5<32))} "
      f"medium(32-96)={int(sum(1 for b in boxes if 32<=(b['pw']*b['ph'])**0.5<96))} "
      f"large(>=96)={int(sum(1 for b in boxes if (b['pw']*b['ph'])**0.5>=96))}")

# per-class table
print(f"\n{'id':<3}{'name':<14}{'inst':>6}{'imgs':>6}{'%':>7}{'med px':>8}{'p05 px':>8}{'p95 px':>8}{'med@1024':>10}")
for c in sorted(set(cls_counts) | set(NAMES)):
    sel = [b for b in boxes if b["cls"] == c]
    if not sel:
        print(f"{c:<3}{NAMES.get(c,'?'):<14}{0:>6}{0:>6}"); continue
    sides = np.array([(b["pw"]*b["ph"])**0.5 for b in sel])
    print(f"{c:<3}{NAMES.get(c,'?'):<14}{len(sel):>6}{len(set(b['stem'] for b in sel)):>6}"
          f"{100*len(sel)/len(boxes):>6.1f}%{np.median(sides):>8.1f}{np.percentile(sides,5):>8.1f}"
          f"{np.percentile(sides,95):>8.1f}{np.median([b['side_i'] for b in sel]):>10.1f}")
print(f"\nCOCO category counts (cross-check): {dict(coco_counts)}")

# duplicate / overlapping boxes within an image
def iou(a, b):
    ix = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    iy = max(0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    inter = ix * iy
    u = a["w"]*a["h"] + b["w"]*b["h"] - inter
    return inter / u if u > 0 else 0
by_img = defaultdict(list)
for b in boxes: by_img[b["stem"]].append(b)
dups, overlaps = [], []
for s, bs in by_img.items():
    for i in range(len(bs)):
        for j in range(i+1, len(bs)):
            v = iou(bs[i], bs[j])
            if v > 0.9: dups.append((s, bs[i]["cls"], bs[j]["cls"], round(v, 3)))
            elif v > 0.4: overlaps.append((s, bs[i]["cls"], bs[j]["cls"], round(v, 3)))
print(f"\nduplicate boxes IoU>0.9: {len(dups)} {dups[:5]}")
print(f"heavy overlap IoU>0.4  : {len(overlaps)} {overlaps[:5]}")

# ---------- CSVs ----------
with open(OUT/"boxes.csv", "w", newline="") as f:
    w_ = csv.DictWriter(f, fieldnames=list(boxes[0].keys())); w_.writeheader(); w_.writerows(boxes)
with open(OUT/"images.csv", "w", newline="") as f:
    w_ = csv.DictWriter(f, fieldnames=list(img_rows[0].keys())); w_.writeheader(); w_.writerows(img_rows)
with open(OUT/"near_duplicates.csv", "w", newline="") as f:
    w_ = csv.writer(f); w_.writerow(["a", "b", "hamming"]); w_.writerows(dup_pairs)
with open(OUT/"per_class.csv", "w", newline="") as f:
    w_ = csv.writer(f); w_.writerow(["id","name","instances","images","median_px","p05_px","p95_px","median_px_at_1024"])
    for c in sorted(cls_counts):
        sel = [b for b in boxes if b["cls"] == c]
        sides = np.array([(b["pw"]*b["ph"])**0.5 for b in sel])
        w_.writerow([c, NAMES.get(c,"?"), len(sel), len(set(b['stem'] for b in sel)),
                     round(float(np.median(sides)),1), round(float(np.percentile(sides,5)),1),
                     round(float(np.percentile(sides,95)),1), round(float(np.median([b['side_i'] for b in sel])),1)])
print(f"\nCSVs -> {OUT}")

# ---------- plots ----------
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(2, 2, figsize=(12, 9))
ax[0,0].hist([(b["pw"]*b["ph"])**0.5 for b in boxes], bins=40); ax[0,0].set_title("sqrt(box area), native px"); ax[0,0].axvline(32, c='r', ls='--')
ax[0,1].hist(side_i, bins=40); ax[0,1].set_title(f"sqrt(box area) @ imgsz {IMGSZ}"); ax[0,1].axvline(16, c='r', ls='--')
ax[1,0].hist([b["ar"] for b in boxes], bins=40); ax[1,0].set_title("aspect ratio w/h")
ax[1,1].scatter([b["xc"] for b in boxes], [b["yc"] for b in boxes], s=6, alpha=.5)
ax[1,1].invert_yaxis(); ax[1,1].set_xlim(0,1); ax[1,1].set_ylim(1,0); ax[1,1].set_title("box centers")
plt.tight_layout(); plt.savefig(OUT/"distributions.png", dpi=110)
print(f"plot -> {OUT/'distributions.png'}")
