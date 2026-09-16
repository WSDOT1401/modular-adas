#!/usr/bin/env python3
"""Deeper checks: COCO<->YOLO agreement, clip/dup topology, empty-image provenance, attrs."""
import json, re
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent / "datasets"
def hdr(t): print(f"\n{'='*70}\n{t}\n{'='*70}")

coco = json.loads((ROOT/"COCO/annotations/instances_default.json").read_text())
imgs = {im["id"]: im for im in coco["images"]}
cat = {c["id"]: c["name"] for c in coco["categories"]}
NAME2ID = {"Regulatory":0, "Warning":1, "Information":2}

# ---------- COCO <-> YOLO numeric agreement ----------
hdr("COCO <-> YOLO AGREEMENT")
coco_by_stem = defaultdict(list)
for a in coco["annotations"]:
    im = imgs[a["image_id"]]
    W, H = im["width"], im["height"]
    x, y, w, h = a["bbox"]
    coco_by_stem[Path(im["file_name"]).stem].append(
        (NAME2ID[cat[a["category_id"]]], (x+w/2)/W, (y+h/2)/H, w/W, h/H))
yolo_by_stem = defaultdict(list)
for p in sorted((ROOT/"YOLO/labels/train").glob("*.txt")):
    for l in p.read_text().splitlines():
        if l.strip():
            c, *v = l.split(); yolo_by_stem[p.stem].append((int(c), *map(float, v)))
bad, maxerr = [], 0.0
for s in set(coco_by_stem) | set(yolo_by_stem):
    a, b = sorted(coco_by_stem[s]), sorted(yolo_by_stem[s])
    if len(a) != len(b): bad.append((s, "count", len(a), len(b))); continue
    for r1, r2 in zip(a, b):
        if r1[0] != r2[0]: bad.append((s, "class", r1[0], r2[0])); continue
        e = max(abs(p-q) for p, q in zip(r1[1:], r2[1:]))
        maxerr = max(maxerr, e)
        if e > 1e-3: bad.append((s, "geom", round(e,5)))
print(f"mismatches: {len(bad)} {bad[:5]}   max coord delta: {maxerr:.2e}")
print("-> the two formats are the same annotations, one export." if not bad else "-> FORMATS DISAGREE")

# ---------- CVAT attributes ----------
hdr("CVAT ATTRIBUTES")
attrs = Counter()
for a in coco["annotations"]:
    for k, v in (a.get("attributes") or {}).items(): attrs[(k, str(v))] += 1
print(dict(attrs))
occ = [a for a in coco["annotations"] if (a.get("attributes") or {}).get("occluded")]
print(f"flagged occluded: {len(occ)} / {len(coco['annotations'])}")
rot = [a for a in coco["annotations"] if (a.get("attributes") or {}).get("rotation")]
print(f"nonzero rotation: {len(rot)}")

# ---------- clip topology + near-dup structure ----------
hdr("CLIP / NEAR-DUPLICATE TOPOLOGY")
img_dir = ROOT/"YOLO/images/train"
stems = sorted(p.stem for p in img_dir.glob("*.jpg"))
clip_re = re.compile(r"^(.*)_f(\d+)$")
clip_of, frame_of = {}, {}
for s in stems:
    m = clip_re.match(s); clip_of[s] = m.group(1); frame_of[s] = int(m.group(2))
H = {}
for s in stems:
    with Image.open(img_dir/f"{s}.jpg") as im:
        g = np.asarray(im.convert("L").resize((9,8), Image.BILINEAR), dtype=np.int16)
    H[s] = np.unpackbits(np.packbits((g[:,1:] > g[:,:-1]).flatten()))
M = np.stack([H[s] for s in stems])
D = (M[:,None,:] != M[None,:,:]).sum(-1)
iu = np.triu_indices(len(stems), 1)
for thr in (3, 5, 8, 10):
    pairs = [(stems[i], stems[j]) for i, j in zip(*iu) if D[i,j] <= thr]
    within = sum(1 for a,b in pairs if clip_of[a]==clip_of[b])
    print(f"hamming<={thr:2d}: {len(pairs):5d} pairs | within-clip {within:5d} | cross-clip {len(pairs)-within:5d}")
pairs5 = [(stems[i], stems[j], int(D[i,j])) for i,j in zip(*iu) if D[i,j] <= 5]
cross = [(a,b,d) for a,b,d in pairs5 if clip_of[a]!=clip_of[b]]
print(f"\ncross-clip near-dups @<=5 (different recordings look identical): {len(cross)}")
print("  examples:", cross[:5])
# connected components at <=5 => "effectively the same scene"
parent = {s:s for s in stems}
def find(x):
    while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
    return x
for a,b,_ in pairs5:
    ra, rb = find(a), find(b)
    if ra!=rb: parent[ra]=rb
comp = defaultdict(list)
for s in stems: comp[find(s)].append(s)
sizes = sorted((len(v) for v in comp.values()), reverse=True)
print(f"\nvisually-distinct groups @hamming<=5: {len(comp)} (from {len(stems)} images); "
      f"largest groups={sizes[:8]}")
print(f"clips: {len(set(clip_of.values()))}")
cc = Counter(clip_of.values())
print("frames per clip:", dict(sorted(cc.items(), key=lambda kv:-kv[1])))

# ---------- empty vs labelled per clip ----------
hdr("EMPTY (BACKGROUND) IMAGES")
empty = [s for s in stems if not yolo_by_stem.get(s)]
print(f"empty: {len(empty)}/{len(stems)}")
per_clip = defaultdict(lambda: [0,0])
for s in stems:
    per_clip[clip_of[s]][0 if yolo_by_stem.get(s) else 1] += 1
print(f"{'clip':<26}{'labelled':>9}{'empty':>7}")
for k,(a,b) in sorted(per_clip.items(), key=lambda kv:-kv[1][1])[:12]:
    print(f"{k:<26}{a:>9}{b:>7}")
fully_empty = [k for k,(a,b) in per_clip.items() if a==0]
print(f"clips with ZERO labels at all: {len(fully_empty)} {fully_empty}")
# do empties sit next to labelled frames in the same clip (=likely missed annotation)?
adj = 0
for s in empty:
    sibs = [t for t in stems if clip_of[t]==clip_of[s] and yolo_by_stem.get(t)]
    if sibs and min(abs(frame_of[t]-frame_of[s]) for t in sibs) <= 450: adj += 1
print(f"empty frames within 450 frames (~15 s @30fps) of a labelled frame in same clip: {adj}/{len(empty)}")
