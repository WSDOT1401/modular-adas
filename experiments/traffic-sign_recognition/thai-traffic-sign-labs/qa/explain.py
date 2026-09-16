#!/usr/bin/env python3
"""Explainer figures for issues 3/5/6/7: side-by-side crops with full stem + class."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parent.parent/"datasets"
OUT=Path(__file__).resolve().parent/"out"
IMG,LBL=ROOT/"YOLO/images/train",ROOT/"YOLO/labels/train"
NAMES={0:"Regulatory",1:"Warning",2:"Information"}; COL={0:(255,60,60),1:(255,200,0),2:(60,160,255)}
def font(sz):
    try: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf",sz)
    except Exception: return ImageFont.load_default()
F,FS=font(20),font(15)
def boxes(s):
    return [(int(p[0]),*map(float,p[1:])) for p in
            (l.split() for l in (LBL/f"{s}.txt").read_text().splitlines() if l.strip())]
def cell(s,b,out=300,pad=2.6):
    im=Image.open(IMG/f"{s}.jpg").convert("RGB"); W,H=im.size
    c,x,y,w,h=b; r=max(w*W,h*H)*pad/2; cx,cy=x*W,y*H
    cr=im.crop((int(cx-r),int(cy-r),int(cx+r),int(cy+r))).resize((out,out),Image.LANCZOS)
    d=ImageDraw.Draw(cr); k=out/(2*r)
    d.rectangle([out/2-w*W*k/2,out/2-h*H*k/2,out/2+w*W*k/2,out/2+h*H*k/2],outline=COL[c],width=3)
    return cr
def sheet(groups,path,cols=4,out=300):
    """groups: list of (caption, [(stem, box_idx), ...])"""
    items=[]
    for cap,refs in groups:
        for s,i in refs:
            b=boxes(s)[i]
            items.append((cell(s,b,out),NAMES[b[0]],f"{s}",cap,COL[b[0]]))
    rows=(len(items)+cols-1)//cols; ch=out+62
    sh=Image.new("RGB",(cols*out,rows*ch),(22,22,22)); d=ImageDraw.Draw(sh)
    for i,(im,cls,stem,cap,col) in enumerate(items):
        r,c=divmod(i,cols); X,Y=c*out,r*ch
        sh.paste(im,(X,Y))
        d.text((X+4,Y+out+3),f"label: {cls}",fill=col,font=F)
        d.text((X+4,Y+out+26),stem,fill=(200,200,200),font=FS)
        d.text((X+4,Y+out+42),cap,fill=(150,220,150),font=FS)
    sh.save(path,quality=94); print(path,len(items))

# ---- #3 class inconsistency: same sign shape, different label
sheet([
 ("yellow diamond",[("20260909_115404_REC_F_f000840",0)]),
 ("yellow diamond",[("2026_0912_014419_f002550",0),("2026_0912_014419_f002550",1)]),
 ("chevron / curve arrow",[("20260909_115504_REC_F_f000840",4)]),
 ("chevron / curve arrow",[("2026_0911_215025_f000000",2),("2026_0911_215025_f000000",4)]),
 ("blue circle",[("2026_0912_012925_f002850",0)]),
 ("blue circle",[("2026_0911_215025_f000000",0)]),
 ("U-turn arrow",[("20260909_115404_REC_F_f000840",1)]),
 ("U-turn arrow",[("2026_0912_025830_f002700",0)]),
], OUT/"issue3_class_inconsistency.jpg", cols=4)

# ---- #5 partial boxes on notice boards
sheet([("red strip only; yellow board unboxed",
        [(s,i) for s,i in [("2026_0912_013224_f005025",0),("2026_0912_020728_f000150",2),
                           ("2026_0912_022821_f002625",0),("2026_0912_022224_f004050",0)]])],
      OUT/"issue5_partial_boxes.jpg", cols=4, out=340)

# ---- #6 border treatment
sheet([
 ("box CUTS INTO the sign",[("2025_1230_004245_f000450",1),("20260909_115404_REC_F_f001200",1),
                            ("20260909_115404_REC_F_f001500",1)]),
 ("box tight on sign face",[("2026_0912_014419_f002550",1)]),
 ("box INCLUDES backing plate",[("2026_0911_215623_f000525",0),("2026_0912_014419_f001125",1)]),
], OUT/"issue6_border.jpg", cols=3, out=340)

# ---- #7 unlearnable night boxes: rank boxes by crop contrast
rows=[]
for p in sorted(LBL.glob("*.txt")):
    for i,b in enumerate(boxes(p.stem) if p.read_text().strip() else []):
        im=Image.open(IMG/f"{p.stem}.jpg"); W,H=im.size
        c,x,y,w,h=b
        cr=np.asarray(im.crop((int((x-w/2)*W),int((y-h/2)*H),int((x+w/2)*W),int((y+h/2)*H))).convert("L"),dtype=float)
        if cr.size: rows.append((float(cr.std()),float(cr.mean()),p.stem,i,c))
rows.sort()
print("\nlowest-contrast boxes (std of pixel values inside the box):")
for st,mn,s,i,c in rows[:12]: print(f"  std={st:5.1f} mean={mn:5.1f} {NAMES[c]:<12}{s} #{i}")
print(f"\nboxes with std<20 (visually near-flat): {sum(1 for r in rows if r[0]<20)}/{len(rows)}")
print(f"boxes with std<15: {sum(1 for r in rows if r[0]<15)}/{len(rows)}")
sheet([("very low contrast",[(s,i) for _,_,s,i,_ in rows[:8]])],
      OUT/"issue7_unlearnable.jpg", cols=4, out=300)
