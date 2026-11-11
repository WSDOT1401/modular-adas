#!/usr/bin/env python3
"""Contact sheets: per-class crops, full frames with boxes, empty frames, odd boxes."""
import random, re, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent / "datasets"
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
IMG = ROOT/"YOLO/images/train"; LBL = ROOT/"YOLO/labels/train"
NAMES = {0:"Regulatory", 1:"Warning", 2:"Information"}
COL = {0:(255,60,60), 1:(255,200,0), 2:(60,160,255)}
random.seed(0)
try: F = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
except Exception: F = ImageFont.load_default()

boxes = defaultdict(list)
for p in sorted(LBL.glob("*.txt")):
    for l in p.read_text().splitlines():
        if l.strip():
            c,x,y,w,h = l.split(); boxes[p.stem].append((int(c),float(x),float(y),float(w),float(h)))
stems = sorted(q.stem for q in IMG.glob("*.jpg"))

def crop(stem, b, pad=1.6, out=192):
    with Image.open(IMG/f"{stem}.jpg") as im:
        W,H = im.size
        c,x,y,w,h = b
        s = max(w*W, h*H)*pad/2
        cx, cy = x*W, y*H
        box = (cx-s, cy-s, cx+s, cy+s)
        c2 = im.convert("RGB").crop(tuple(map(int,box))).resize((out,out), Image.LANCZOS)
    d = ImageDraw.Draw(c2)
    k = out/(2*s)
    d.rectangle([out/2-w*W*k/2, out/2-h*H*k/2, out/2+w*W*k/2, out/2+h*H*k/2], outline=COL[c], width=2)
    d.text((3,3), f"{int(round(w*W))}x{int(round(h*H))}", fill=(0,255,0), font=F,
           stroke_width=2, stroke_fill=(0,0,0))
    return c2

def sheet(items, path, cols=8, cell=192, cap=28):
    rows = (len(items)+cols-1)//cols
    sh = Image.new("RGB", (cols*cell, rows*(cell+cap)), (20,20,20))
    d = ImageDraw.Draw(sh)
    for i,(img,txt) in enumerate(items):
        r,c = divmod(i, cols)
        sh.paste(img, (c*cell, r*(cell+cap)))
        d.text((c*cell+3, r*(cell+cap)+cell+5), txt[:34], fill=(230,230,230), font=F)
    sh.save(path, quality=92); print(f"{path}  ({len(items)} cells)")

# 1. per-class crop sheets, sorted small->large
for cid, nm in NAMES.items():
    sel = [(s,b) for s in stems for b in boxes[s] if b[0]==cid]
    with_px = sorted(sel, key=lambda sb: sb[1][3]*sb[1][4])
    idx = np.linspace(0, len(with_px)-1, min(32, len(with_px))).astype(int)
    items = [(crop(with_px[i][0], with_px[i][1]), f"{with_px[i][0][-18:]}") for i in idx]
    sheet(items, OUT/f"class_{cid}_{nm}.jpg")

# 2. full frames w/ boxes (sample incl. multi-box + smallest boxes)
def full(stem, w=1100):
    with Image.open(IMG/f"{stem}.jpg") as im:
        im = im.convert("RGB"); W,H = im.size
        d = ImageDraw.Draw(im)
        for c,x,y,bw,bh in boxes[stem]:
            d.rectangle([(x-bw/2)*W,(y-bh/2)*H,(x+bw/2)*W,(y+bh/2)*H], outline=COL[c], width=5)
            d.text(((x-bw/2)*W, (y-bh/2)*H-30), f"{NAMES[c]} {int(bw*W)}x{int(bh*H)}",
                   fill=COL[c], font=F, stroke_width=3, stroke_fill=(0,0,0))
        return im.resize((w, int(H*w/W)), Image.LANCZOS)
multi = sorted([s for s in stems if len(boxes[s])>=3], key=lambda s:-len(boxes[s]))[:6]
smallest = sorted([s for s in stems if boxes[s]],
                  key=lambda s: min(b[3]*b[4] for b in boxes[s]))[:6]
for tag, group in (("multi", multi), ("smallest", smallest)):
    ims = [full(s, 900) for s in group]
    Wd = max(i.width for i in ims); Ht = sum(i.height for i in ims)
    sh = Image.new("RGB",(Wd,Ht),(0,0,0)); yy=0
    for s,i in zip(group, ims):
        sh.paste(i,(0,yy)); ImageDraw.Draw(sh).text((6,yy+6), s, fill=(0,255,0), font=F,
                                                    stroke_width=2, stroke_fill=(0,0,0)); yy+=i.height
    sh.save(OUT/f"frames_{tag}.jpg", quality=88); print(OUT/f"frames_{tag}.jpg")

# 3. empty frames — are there unlabelled signs?
empty = [s for s in stems if not boxes[s]]
pick = random.sample(empty, min(12, len(empty)))
ims = [full(s, 760) for s in pick]
cols=3; rows=(len(ims)+cols-1)//cols
cw, ch = ims[0].width, ims[0].height
sh = Image.new("RGB",(cols*cw, rows*(ch+26)),(15,15,15))
for i,(s,im) in enumerate(zip(pick,ims)):
    r,c = divmod(i,cols); sh.paste(im,(c*cw, r*(ch+26)))
    ImageDraw.Draw(sh).text((c*cw+4, r*(ch+26)+ch+4), s, fill=(255,255,255), font=F)
sh.save(OUT/"empty_frames.jpg", quality=86); print(OUT/"empty_frames.jpg", pick)

# 4. odd aspect ratios + biggest boxes
odd = []
for s in stems:
    for b in boxes[s]:
        with Image.open(IMG/f"{s}.jpg") as im: W,H = im.size
        ar = (b[3]*W)/(b[4]*H)
        if ar > 1.8 or ar < 0.6: odd.append((ar, s, b))
odd.sort(key=lambda t:-t[0])
items = [(crop(s,b), f"ar={ar:.2f} {NAMES[b[0]]}") for ar,s,b in (odd[:16]+odd[-8:])]
sheet(items, OUT/"odd_aspect.jpg")
print(f"odd-aspect boxes (ar>1.8 or <0.6): {len(odd)}")

# 5. the 73-image near-dup cluster: is it real or a dHash artifact on dark frames?
bright = {}
for s in stems:
    with Image.open(IMG/f"{s}.jpg") as im:
        bright[s] = float(np.asarray(im.convert("L").resize((64,36))).mean())
b = np.array(list(bright.values()))
print(f"\nframe mean brightness: p05={np.percentile(b,5):.0f} med={np.median(b):.0f} p95={np.percentile(b,95):.0f}")
dark = [s for s,v in bright.items() if v < 60]
print(f"frames with mean luma <60 (night): {len(dark)}/{len(stems)}")
night_boxes = sum(len(boxes[s]) for s in dark)
print(f"boxes in those night frames: {night_boxes}/{sum(len(v) for v in boxes.values())}")
dk = random.sample(dark, min(6,len(dark))) if dark else []
if dk:
    ims=[full(s,760) for s in dk]; cw,ch=ims[0].width,ims[0].height
    sh=Image.new("RGB",(3*cw,2*(ch+26)),(15,15,15))
    for i,(s,im) in enumerate(zip(dk,ims)):
        r,c=divmod(i,3); sh.paste(im,(c*cw,r*(ch+26)))
        ImageDraw.Draw(sh).text((c*cw+4,r*(ch+26)+ch+4), f"{s} luma={bright[s]:.0f}", fill=(255,255,255), font=F)
    sh.save(OUT/"night_frames.jpg", quality=86); print(OUT/"night_frames.jpg")
