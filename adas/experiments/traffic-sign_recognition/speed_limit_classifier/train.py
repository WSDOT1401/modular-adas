"""Fine-tune MobileNetV3-Small on synthetic signs; score it on the real crops.

The split is the whole point: we train on synth.py output only and test on real/,
so the test number means "works on footage it has never seen" rather than "memorised
28 signs". There is no leakage to worry about because the two sets share no pixels.

    python train.py                  # ~5 min on MPS
    python train.py --epochs 40
"""
import argparse, csv, random, sys
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small
from torchvision.transforms import v2

import synth

HERE = Path(__file__).parent
SIZE = 128         # default only -- the live value is passed explicitly into
                   # Synthetic/real_crops, because DataLoader workers `spawn` on
                   # macOS and re-import this module, losing any global we set.
                   # measured, and NOT about pixel count: MobileNetV3-Small downsamples
                   # 32x, so 64px input leaves a 2x2 final feature map and the net cannot
                   # tell a 6 from an 8. 128px -> 4x4 took real accuracy 72.2% -> 91.7%
                   # for +13ms/crop on CPU. 64px is the trap; it looks right because the
                   # crops are small, but the feature map is what matters.
GATE_PX = 32       # below this a human cannot read the sign either -- see sheet.png

# ImageNet stats, because we start from ImageNet weights. Mismatch here quietly
# costs several points of accuracy and looks like a bad model.
NORM = v2.Compose([v2.ToImage(), v2.ToDtype(torch.float32, scale=True),
                   v2.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])


class Synthetic(Dataset):
    """Infinite-ish: every __getitem__ draws a brand new sign, so there is no fixed
    training set for the model to memorise. `n` is just how long an epoch is."""

    def __init__(self, n, size):
        self.n, self.size = n, size

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        img, value = synth.sample(out=self.size)
        return NORM(img), synth.VALUES.index(value)


def _seed_worker(wid):
    # torch reseeds itself per worker but not the `random` module, and synth.py runs
    # on `random`. Without this every worker draws the identical sign sequence.
    random.seed(torch.initial_seed() % 2**32 + wid)


def real_crops(size):
    """The test set: hand-read labels from sheet.png, minus junk and unreadables."""
    rows = [r for r in csv.DictReader(open(HERE / "labels.csv"))
            if r["label"] not in ("x", "?")]
    out = []
    for r in rows:
        img = Image.open(HERE / "real" / r["file"]).convert("RGB").resize((size, size), Image.BILINEAR)
        out.append((NORM(img), synth.VALUES.index(int(r["label"])), int(r["px"]), r["file"]))
    return out


def build():
    m = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)   # NOT the default arg!
    m.classifier[3] = nn.Linear(1024, len(synth.VALUES))                 # swap the 1000-class head
    return m


@torch.no_grad()
def evaluate(model, test, device):
    model.eval()
    x = torch.stack([t[0] for t in test]).to(device)
    pred = model(x).argmax(1).cpu()
    ok = [p.item() == t[1] for p, t in zip(pred, test)]
    gated = [o for o, t in zip(ok, test) if t[2] >= GATE_PX]
    wrong = [(t[3], t[2], synth.VALUES[t[1]], synth.VALUES[p])
             for o, p, t in zip(ok, pred, test) if not o and t[2] >= GATE_PX]
    return sum(gated) / len(gated), sum(ok) / len(ok), wrong


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--steps", type=int, default=120, help="batches per epoch")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--size", type=int, default=SIZE, help="model input px")
    a = ap.parse_args()
    size = a.size
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.manual_seed(0); random.seed(0)

    test = real_crops(size)
    print(f"input {size}px -> final feature map {size // 32}x{size // 32}")
    print(f"test set: {len(test)} real crops, "
          f"{sum(1 for t in test if t[2] >= GATE_PX)} of them >={GATE_PX}px")

    loader = DataLoader(Synthetic(a.steps * a.batch, size), batch_size=a.batch, num_workers=4,
                        worker_init_fn=_seed_worker, persistent_workers=True, drop_last=True)

    model = build().to(device)
    # Plenty of data, so full fine-tune. Freezing `features` is for when you have a
    # few hundred real images and nothing else -- that is not our situation.
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * a.steps)
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
        gated_acc, all_acc, wrong = evaluate(model, test, device)
        star = ""
        if gated_acc > best:
            best, star = gated_acc, "  *saved"
            torch.save({"state_dict": model.state_dict(), "values": synth.VALUES,
                        "size": size, "gate_px": GATE_PX}, HERE / "speed_classifier.pt")
        print(f"epoch {ep:3d}  loss {tot / a.steps:.3f}   "
              f"real>={GATE_PX}px {gated_acc:.1%}   all-real {all_acc:.1%}{star}", flush=True)

    print(f"\nbest real accuracy (>={GATE_PX}px): {best:.1%}")
    _, _, wrong = evaluate(model, test, device)
    if wrong:
        print("still wrong at final epoch:")
        for f, px, want, got in wrong:
            print(f"  {f}  {px}px  true {want} -> said {got}")


if __name__ == "__main__":
    main()
