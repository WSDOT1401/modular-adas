"""Read the number off a speed-limit crop. This is the part that ships to the Pi.

    from classify import SpeedClassifier, SignVote
    clf, vote = SpeedClassifier(), SignVote()
    for frame, boxes in stream:
        for box in boxes:                       # boxes the detector called speed_limit
            value, conf = clf(frame, box)
            if (settled := vote.update(value)):
                announce(settled)               # fires once per physical sign

    python classify.py          # self-check against real/
"""
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from torchvision.models import mobilenet_v3_small
from torchvision.transforms import v2

HERE = Path(__file__).parent
CKPT = HERE / "speed_classifier.pt"

# Two gates, both measured rather than guessed:
GATE_PX = 32      # narrower than this and the digits are mush -- see sheet.png
CONF_MIN = 0.60   # measured: keeps 31/33 correct answers while dropping 1 of 3 wrong
                  # ones. The separation is weak (a junk crop scored 0.92), so this is
                  # a mild filter, not a guarantee -- SignVote is the real defence.

NORM = v2.Compose([v2.ToImage(), v2.ToDtype(torch.float32, scale=True),
                   v2.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])


class SpeedClassifier:
    def __init__(self, ckpt=CKPT, device="cpu"):
        # cpu by default: this runs on a Pi, and it only fires on a detection, so
        # the ~50ms is paid a few times a minute, not 30 times a second.
        blob = torch.load(ckpt, map_location=device, weights_only=True)
        self.values, self.size = blob["values"], blob["size"]
        self.model = mobilenet_v3_small(num_classes=len(self.values))
        self.model.load_state_dict(blob["state_dict"])
        self.model.eval().to(device)
        self.device = device

    def crop(self, frame, box):
        """Square up the detector box the same way crops.py did, or the sign comes
        out squashed and nothing matches training."""
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        half = max(x1 - x0, y1 - y0) * 0.6          # 1.2x box = the 10% margin crops.py used
        if isinstance(frame, Image.Image):
            return frame.crop((max(0, cx - half), max(0, cy - half),
                               min(frame.width, cx + half), min(frame.height, cy + half)))
        h, w = frame.shape[:2]                      # numpy BGR straight from the detector
        a = frame[max(0, int(cy - half)):min(h, int(cy + half)),
                  max(0, int(cx - half)):min(w, int(cx + half))]
        return Image.fromarray(a[..., ::-1].copy())  # BGR->RGB; copy the crop, not the frame

    @torch.no_grad()
    def __call__(self, frame, box):
        """-> (speed, confidence). speed is None when we decline to guess."""
        return self.read(self.crop(frame, box), box[2] - box[0])

    @torch.no_grad()
    def read(self, crop, px):
        """Classify an already-cropped sign. `px` is the detector box width, used for
        the legibility gate -- not the crop's own width, which is 1.2x larger."""
        if px < GATE_PX:
            return None, 0.0                        # too small to read: say "speed limit", no number
        img = crop.convert("RGB").resize((self.size, self.size), Image.BILINEAR)
        probs = self.model(NORM(img).unsqueeze(0).to(self.device)).softmax(1)[0]
        conf, idx = probs.max(0)
        if conf.item() < CONF_MIN:
            return None, conf.item()                # probably not a speed limit at all
        return self.values[idx], conf.item()


class SignVote:
    """One sign is seen over many frames, growing as you approach. Voting across them
    turns a good-per-frame classifier into a near-certain per-sign one, and it is the
    cheapest accuracy on offer.

    ponytail: no IoU tracking -- two *different* speed limits visible at once is
    vanishingly rare on a road, so "detections close together in time" is the same
    sign. Add real track IDs if the sign detector ever runs on motorway gantries.
    """

    def __init__(self, min_votes=3, gap_frames=12):
        self.min_votes, self.gap_frames = min_votes, gap_frames
        self.votes, self.idle, self.fired = Counter(), 0, False

    def update(self, value):
        """Call once per frame; pass None when no speed-limit sign was detected.
        Returns the speed exactly once per sign, else None."""
        if value is None:
            self.idle += 1
            if self.idle > self.gap_frames:         # sign has left the frame; rearm
                self.votes.clear(); self.fired = False
            return None
        self.idle = 0
        self.votes[value] += 1
        best, n = self.votes.most_common(1)[0]
        if n >= self.min_votes and not self.fired:
            self.fired = True
            return best
        return None


def selfcheck():
    """Two checks, because they fail for different reasons.

    1. crop() geometry, asserted exactly -- this is the piece that silently shifts the
       sign off-centre and costs accuracy without ever raising.
    2. the model path over real/, which must agree with train.py's eval. If these two
       disagree, inference preprocesses differently from training.
    """
    import csv

    # --- 1. crop geometry: a 40x40 box at (100,100) must give a 48px square around it
    clf = SpeedClassifier()
    frame = Image.new("RGB", (640, 480))
    got = clf.crop(frame, (100, 100, 140, 140))
    assert got.size == (48, 48), f"expected a 1.2x square crop, got {got.size}"
    edge = clf.crop(frame, (0, 0, 40, 40))                  # clamped at the frame edge
    assert edge.size == (44, 44), f"edge crop wrong: {edge.size}"

    # --- 2. the model path. real/*.png IS already the 1.2x crop, so feed it straight in.
    rows = list(csv.DictReader(open(HERE / "labels.csv")))
    hit = miss = declined = 0
    for r in rows:
        px, img = int(r["px"]), Image.open(HERE / "real" / r["file"]).convert("RGB")
        value, conf = clf.read(img, px)
        if r["label"] in ("x", "?"):
            declined += value is None
            continue
        if px < GATE_PX:
            continue
        if value == int(r["label"]):
            hit += 1
        else:
            miss += 1
            print(f"  miss {r['file']} {px}px  true {r['label']} -> {value} ({conf:.2f})")
    junk = sum(1 for r in rows if r["label"] in ("x", "?"))
    print(f"\nreal crops >={GATE_PX}px: {hit}/{hit + miss} correct")
    print(f"junk/unreadable declined: {declined}/{junk}")
    # A loose floor on purpose. This check exists to catch the *catastrophic* failure
    # -- inference preprocessing drifting from training, which scores ~25% -- not to
    # police model quality. With n=36 the 95% CI is about +-9%, so a tight threshold
    # here would fail on pure noise and teach everyone to ignore the check.
    assert hit / (hit + miss) > 0.60, f"only {hit}/{hit + miss}: preprocessing likely broken"
    print("crop geometry OK; inference matches training")


if __name__ == "__main__":
    selfcheck()
