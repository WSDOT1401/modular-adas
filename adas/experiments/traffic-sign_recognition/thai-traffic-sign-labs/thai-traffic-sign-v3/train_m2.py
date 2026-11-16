#!/usr/bin/env python3
"""Train M2: given a crop, say which sign it is.

    python train_m2.py                 # ~10 min on MPS
    python train_m2.py --epochs 40

Trains on 29 classes, shows 13. The other 16 -- the helpers and the reject
class -- all mean "dash stays quiet", which is identical on screen to rejecting
them and a far easier thing to learn than one "other" bucket.

Training data is real crops from m2/train PLUS fresh synthetic signs drawn by
m2_synth.py every single batch, so the 12 pictogram classes are never short.
Scoring is real crops only, from clips the model never trained on.

The headline is the MACRO average over the 13 displayed classes: `information`
is 150 of 870 val crops, so a micro number is mostly a report card on blue
boards. Classes with fewer than 5 real val crops print `not scored` instead of
a number, because a 2-crop class can only score 0/50/100 and would still get a
full vote in the average.
"""
import argparse
import collections
import random
import sys
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small
from torchvision.transforms import v2

import m2_synth

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import classes  # noqa: E402

CLASSES = list(classes.THAI_FINE_NAMES) + ["not_a_sign"]
IDX = {n: i for i, n in enumerate(CLASSES)}
DISPLAYED = classes.THAI_FINE_DISPLAYED
QUIET = [n for n in CLASSES if n not in DISPLAYED]
MIN_N = 5          # below this, a per-class accuracy is noise wearing a % sign
SIZE = m2_synth.SIZE

# ImageNet stats, because we start from ImageNet weights. A mismatch here
# quietly costs several points and looks like a bad model.
NORM = v2.Compose([v2.ToImage(), v2.ToDtype(torch.float32, scale=True),
                   v2.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
# No flips: left and right are the whole difference between two of our classes.
AUG = v2.Compose([v2.RandomResizedCrop(SIZE, scale=(0.7, 1.0), antialias=True),
                  v2.ColorJitter(0.3, 0.3, 0.25)])


class Mixed(Dataset):
    """Real crops, then synthetic ones. A synthetic index has a fixed class and
    a brand new drawing every time it is asked for, so there is nothing to
    memorise and the rare classes never run out."""

    def __init__(self, real, n_synth, train=True):
        self.real, self.train = real, train
        self.synth = [m2_synth.CLASSES[i % len(m2_synth.CLASSES)] for i in range(n_synth)]
        self.labels = [IDX[n] for _p, n in real] + [IDX[n] for n in self.synth]

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        if i < len(self.real):
            img = Image.open(self.real[i][0]).convert("RGB")
            img = AUG(img) if self.train else img
        else:
            img, _name = m2_synth.sample(self.synth[i - len(self.real)])
        return NORM(img), self.labels[i]


def crops(split):
    return [(p, d.name) for d in sorted((HERE / "m2" / split).iterdir()) if d.is_dir()
            for p in sorted(d.glob("*.jpg"))]


def _seed_worker(wid):
    # torch reseeds itself per worker but not the `random` module, and
    # m2_synth runs on `random`. Without this every worker draws the same signs.
    random.seed(torch.initial_seed() % 2**32 + wid)


@torch.no_grad()
def evaluate(model, val, device, batch=256):
    model.eval()
    pred = []
    for i in range(0, len(val), batch):
        x = torch.stack([NORM(Image.open(p).convert("RGB"))
                         for p, _n in val[i:i + batch]]).to(device)
        pred += model(x).argmax(1).cpu().tolist()
    hit = collections.Counter()
    n = collections.Counter()
    confused = collections.defaultdict(collections.Counter)
    for (_p, name), got in zip(val, pred):
        n[name] += 1
        if CLASSES[got] == name:
            hit[name] += 1
        else:
            confused[name][CLASSES[got]] += 1
    scored = [c for c in DISPLAYED if n[c] >= MIN_N]
    macro = sum(hit[c] / n[c] for c in scored) / len(scored) if scored else 0.0
    # The second number that matters: when the sign is NOT one of the 13, does
    # the dash stay quiet? Naming the wrong helper class is invisible to a
    # driver; lighting up the dash is not.
    q_n = sum(n[c] for c in QUIET)
    q_ok = sum(n[c] - sum(v for k, v in confused[c].items() if k in DISPLAYED)
               for c in QUIET)
    return macro, scored, hit, n, confused, (q_ok / q_n if q_n else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--synth", type=int, default=2400, help="synthetic crops per epoch")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--reject-weight", type=float, default=1.0,
                    help="not_a_sign's share of an epoch, relative to every "
                         "other class. 1.0 = equal (the sampler below already "
                         "equalises, so the 59%% of crops that are not_a_sign "
                         "is NOT what the model trains on). Below 1.0 trades "
                         "rejection accuracy for `information` recall.")
    a = ap.parse_args()

    device = ("cuda" if torch.cuda.is_available() else
              "mps" if torch.backends.mps.is_available() else "cpu")
    torch.manual_seed(0); random.seed(0)

    train, val = crops("train"), crops("val")
    ds = Mixed(train, a.synth)
    # Inverse-frequency sampling, over real and synthetic together: without it
    # one epoch is 43% not_a_sign and 15% information, and the model can score
    # well on the micro number while never once saying `merge`.
    freq = collections.Counter(ds.labels)
    # ds.labels holds class INDICES, not names. Comparing against the string
    # here silently did nothing for one whole run -- the flag printed in the
    # header, the weights never changed, and because training is seeded the
    # result was bit-identical to the run it was meant to differ from.
    reject = IDX["not_a_sign"]
    base = [1.0 / freq[l] for l in ds.labels]
    w = [b * (a.reject_weight if l == reject else 1.0)
         for b, l in zip(base, ds.labels)]
    assert a.reject_weight == 1.0 or w != base, \
        "--reject-weight had no effect on the sampler weights"
    sampler = WeightedRandomSampler(w, num_samples=len(ds), replacement=True)
    loader = DataLoader(ds, batch_size=a.batch, sampler=sampler, drop_last=True,
                        num_workers=a.workers, worker_init_fn=_seed_worker,
                        persistent_workers=a.workers > 0)

    print(f"{device}  {len(train)} real + {a.synth} synthetic per epoch, "
          f"{len(val)} real val crops, {len(CLASSES)} classes at {SIZE}px"
          + (f", reject-weight {a.reject_weight}" if a.reject_weight != 1.0 else ""))

    model = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)
    model.classifier[3] = nn.Linear(1024, len(CLASSES))     # swap the 1000-class head
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    steps = len(ds) // a.batch
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * steps)
    lossf = nn.CrossEntropyLoss(label_smoothing=0.05)

    best = 0.0
    for ep in range(1, a.epochs + 1):
        model.train()
        tot = 0.0
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = lossf(model(x), y)
            loss.backward()
            opt.step(); sched.step()
            tot += loss.item()
        macro, scored, hit, n, confused, quiet = evaluate(model, val, device)
        star = ""
        if macro > best:
            best, star = macro, "  *saved"
            torch.save({"state_dict": model.state_dict(), "classes": CLASSES,
                        "displayed": list(DISPLAYED), "size": SIZE},
                       HERE / "m2_classifier.pt")
        print(f"epoch {ep:3d}  loss {tot / steps:.3f}   macro@{len(scored)} "
              f"{macro:.1%}   quiet {quiet:.1%}{star}", flush=True)

    model.load_state_dict(torch.load(HERE / "m2_classifier.pt")["state_dict"])
    macro, scored, hit, n, confused, quiet = evaluate(model, val, device)
    print(f"\n{'sign on the dash':24s} {'n':>4s}  {'accuracy':>9s}   most often called")
    print("-" * 74)
    for c in DISPLAYED:
        if n[c] >= MIN_N:
            top = ", ".join(f"{k} x{v}" for k, v in confused[c].most_common(2))
            print(f"{c:24s} {n[c]:4d}  {hit[c] / n[c]:8.1%}   {top}")
        else:
            print(f"{c:24s} {n[c]:4d}  {'not scored':>9s}   (needs {MIN_N} real val crops)")
    print("-" * 74)
    print(f"{'MACRO over ' + str(len(scored)):24s} {sum(n[c] for c in scored):4d}  {macro:8.1%}")
    print(f"{'dash stays quiet':24s} {sum(n[c] for c in QUIET):4d}  {quiet:8.1%}"
          f"   (the 16 classes the driver never sees)")


if __name__ == "__main__":
    main()
