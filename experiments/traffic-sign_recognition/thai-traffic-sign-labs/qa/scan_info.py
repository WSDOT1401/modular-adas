#!/usr/bin/env python3
"""Render every box of one class as a labelled crop grid, for manual scanning."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parent.parent/"datasets"
OUT=Path(__file__).resolve().parent/"out"
IMG,LBL=ROOT/"YOLO/images/train",ROOT/"YOLO/labels/train"
COL={0:(255,60,60),1:(255,200,0),2:(60,160,255)}
def font(s):
    try: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf",s)
    except Exception: return ImageFont.load_default()
F=font(13)
TARGET=int(sys.argv[1]); PER=int(sys.argv[2]) if len(sys.argv)>2 else 60
refs=[]
for p in sorted(LBL.glob("*.txt")):
    for i,l in enumerate([l for l in p.read_text().splitlines() if l.strip()]):
        v=l.split()
        if int(v[0])==TARGET: refs.append((p.stem,i,tuple(map(float,v[1:]))))
print(f"class {TARGET}: {len(refs)} boxes")
CELL=170
for page in range(0,len(refs),PER):
    chunk=refs[page:page+PER]; cols=10
    rows=(len(chunk)+cols-1)//cols; ch=CELL+30
    sh=Image.new("RGB",(cols*CELL,rows*ch),(20,20,20)); d=ImageDraw.Draw(sh)
    for k,(stem,i,(x,y,w,h)) in enumerate(chunk):
        im=Image.open(IMG/f"{stem}.jpg").convert("RGB"); W,H=im.size
        r=max(w*W,h*H)*2.2/2
        cr=im.crop((int(x*W-r),int(y*H-r),int(x*W+r),int(y*H+r))).resize((CELL,CELL),Image.LANCZOS)
        dd=ImageDraw.Draw(cr); kk=CELL/(2*r)
        dd.rectangle([CELL/2-w*W*kk/2,CELL/2-h*H*kk/2,CELL/2+w*W*kk/2,CELL/2+h*H*kk/2],outline=COL[TARGET],width=2)
        R,C=divmod(k,cols); sh.paste(cr,(C*CELL,R*ch))
        d.text((C*CELL+2,R*ch+CELL+2),f"{stem[-13:]} #{i}",fill=(225,225,225),font=F)
    out=OUT/f"scan_cls{TARGET}_p{page//PER}.jpg"; sh.save(out,quality=91); print(out,len(chunk))
