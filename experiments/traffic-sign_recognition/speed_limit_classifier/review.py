#!/usr/bin/env python3
"""Spot-check labels.csv by eye.

    python review.py             # -> http://localhost:8765
    python review.py --selfcheck # CSV round-trip check, no server

Every crop shown next to its hand-read label, grouped by label so an odd one
out in a group of 30s is obvious. Change a dropdown, hit Save, labels.csv is
rewritten in place (previous contents kept as labels.csv.bak).
"""
import csv, http.server, sys, urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
CSV = HERE / "labels.csv"
GATE_PX = 32  # train.py's legibility gate: rows under it are not in the test set
CHOICES = "20 30 40 45 50 60 70 80 90 100 110 120 x ?".split()
PORT = 8765

CSS = """
body{font:14px system-ui;margin:0;background:#1b1b1b;color:#eee}
.bar{position:sticky;top:0;display:flex;gap:12px;align-items:center;
     background:#222;padding:10px 14px;border-bottom:1px solid #444}
button{margin-left:auto;padding:6px 18px;font:inherit}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;padding:14px}
.card{background:#2a2a2a;border-radius:6px;padding:8px;display:flex;flex-direction:column;gap:6px}
.card.dim{opacity:.45}
img{width:100%;aspect-ratio:1;object-fit:contain;image-rendering:pixelated;background:#000}
.cap{color:#999;font-size:12px}
select{font:inherit;width:100%}
"""


def load(path=CSV):
    with path.open() as f:
        return list(csv.DictReader(f))


def save(rows, path=CSV):
    if path.exists():
        path.with_name(path.name + ".bak").write_bytes(path.read_bytes())
    with path.open("w", newline="") as f:
        # lineterminator: DictWriter defaults to \r\n, which rewrites every line
        # of a file we only meant to touch one field of.
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def order(r):
    """Numeric labels first and in numeric order, then x/?; clearest crop first."""
    d = r["label"].isdigit()
    return (not d, int(r["label"]) if d else r["label"], -int(r["px"]))


def page(rows):
    cards = []
    for r in sorted(rows, key=order):
        opts = "".join('<option%s>%s</option>' % (" selected" if c == r["label"] else "", c)
                       for c in CHOICES)
        cards.append(
            '<label class="card%s"><img src="real/%s" loading=lazy>'
            '<div class=cap>#%s &middot; %spx</div><select name=%s>%s</select></label>'
            % (" dim" if int(r["px"]) < GATE_PX else "", r["file"], r["idx"], r["px"],
               r["idx"], opts))
    return ("<!doctype html><meta charset=utf-8><title>labels.csv</title><style>%s</style>"
            "<form method=post action=/save><div class=bar><b>%d crops</b>"
            "<span class=cap>dimmed = under %dpx, excluded from the test set</span>"
            "<button>Save</button></div><div class=grid>%s</div></form>"
            % (CSS, len(rows), GATE_PX, "".join(cards)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def do_GET(self):
        if self.path != "/":
            return super().do_GET()          # serves real/*.png for free
        body = page(load()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        rows = load()
        new = {r["idx"]: form.get(r["idx"], [r["label"]])[0] for r in rows}
        changed = [(r["file"], r["label"], new[r["idx"]]) for r in rows if new[r["idx"]] != r["label"]]
        for r in rows:
            r["label"] = new[r["idx"]]
        save(rows)
        print("saved: %d changed" % len(changed)
              + "".join("\n  %s: %s -> %s" % c for c in changed), flush=True)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def selfcheck():
    import shutil, tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "labels.csv"
        shutil.copy(CSV, p)
        before = p.read_text()
        save(load(p), p)
        assert p.read_text() == before, "round-trip rewrote the file"
        rows = load(p)
        rows[0]["label"] = "?"
        save(rows, p)
        after = load(p)
        assert after[0]["label"] == "?" and len(after) == len(rows), "edit did not land"
        assert [a["file"] for a in after] == [b["file"] for b in rows], "row order moved"
        assert (Path(d) / "labels.csv.bak").read_text() == before, "no usable backup"
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        print("http://localhost:%d   (ctrl-c to stop)" % PORT, flush=True)
        http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
