#!/usr/bin/env python3
"""[2/4] Label a crop by clicking its class -- or confirm the one the VLM picked.

    python sort.py --dir work/gold

The folders under ``<dir>/labels/<person>/`` ARE the config: whoever has a
directory is a labeller, and their subfolders are the class list. Add a class by
creating a folder; there is nothing else to edit, so a folder name can never
drift from classes.py.

Two modes, and which one you are in is the difference between measuring a
pre-annotator and actually being paid by it:

* **blind** (no predictions file) -- for building the answer key. You see a crop
  and nothing else. Used once, at step 0.
* **review** (``<dir>/predictions.csv`` exists) -- the VLM's answer is already
  selected and Enter accepts it. This is where the pipeline saves your group
  work: ~19 class choices collapse into one keypress for every crop the model
  got right, and you only think hard about the rest.

Review mode appends to ``<dir>/review_log.csv``. The accept rate in that file is
the honest "how much work did the model save us" number -- not the VLM's offline
accuracy, which was measured on crops nobody had to fix.

Undo (``u``) is not optional in either mode: a misclick writes a wrong label that
every later number is measured against.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import shutil
import tkinter as tk

from PIL import Image, ImageTk

VIEW = 420  # px the crop is displayed at; crops are ~256px, so this upscales


class Sorter:
    def __init__(self, root, person, pred, log):
        self.root, self.person, self.pred, self.log = root, person, pred, log
        self.classes = sorted(d.name for d in person.iterdir()
                              if d.is_dir() and not d.name.startswith("_"))
        self.queue = sorted((person / "_unsorted").glob("*.jpg"))
        self.ctx = person.parent.parent / "crops_ctx"
        self.wide = False
        self.done = []        # (moved_to, came_from, predicted) -- the undo stack
        self.accepted = 0

        self.image = tk.Label(root)
        self.image.pack(pady=8)
        self.status = tk.Label(root, font=("", 13))
        self.status.pack()

        # Review mode's whole point is that the common case is one key. It gets a
        # button of its own rather than a highlighted entry in the grid of 20,
        # because hunting for the highlight is the work we are trying to remove.
        self.accept = tk.Button(root, text="", command=self.take, state="disabled")
        self.accept.pack(pady=(8, 0), ipadx=12, ipady=6)
        if not pred:
            self.accept.pack_forget()

        grid = tk.Frame(root)
        grid.pack(padx=10, pady=10)
        for i, name in enumerate(self.classes):
            tk.Button(grid, text=name.replace("_", " "), width=16,
                      command=lambda n=name: self.put(n)).grid(row=i // 5, column=i % 5,
                                                               padx=2, pady=2)

        tk.Button(root, text="undo (u)      context view (c)",
                  command=self.undo).pack(pady=(0, 10))
        root.bind("u", lambda _: self.undo())
        root.bind("c", lambda _: self.toggle())
        root.bind("<Return>", lambda _: self.take())
        root.bind("<space>", lambda _: self.take())
        self.show()

    # --- the current crop -------------------------------------------------
    def guess(self):
        return self.pred.get(self.queue[0].stem) if self.queue else None

    def show(self):
        if not self.queue:
            rate = f"   {self.accepted}/{len(self.done)} accepted as-is" if self.pred else ""
            self.image.config(image="", text="all done", font=("", 24), height=10)
            self.status.config(text=f"{len(self.done)} sorted{rate}")
            self.accept.config(text="", state="disabled")
            return

        src = self.queue[0]
        wide = self.ctx / src.name
        crop = Image.open(wide if self.wide and wide.exists() else src)
        scale = VIEW / max(crop.size)
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(crop)  # hold a reference or tkinter frees it
        self.image.config(image=self.photo, text="", height=0)

        g = self.guess()
        self.accept.config(text=f"✓  {g.replace('_', ' ')}   (enter)" if g else "— no guess —",
                           state="normal" if g else "disabled")
        self.status.config(text=f"{src.stem}     {len(self.done) + 1} / "
                                f"{len(self.done) + len(self.queue)}"
                                + ("     [context]" if self.wide else ""))

    def toggle(self):
        self.wide = not self.wide
        self.show()

    def take(self):
        if self.guess() in self.classes:
            self.accepted += 1
            self.put(self.guess())

    # --- moving files -----------------------------------------------------
    def put(self, name):
        if not self.queue:
            return
        src = self.queue.pop(0)
        guess = self.pred.get(src.stem, "")
        dest = self.person / name / src.name
        shutil.move(src, dest)
        self.done.append((dest, src, guess))
        if self.pred:
            self._log(src.stem, guess, name)
        self.wide = False
        self.show()

    def undo(self):
        if not self.done:
            return
        dest, src, guess = self.done.pop()
        shutil.move(dest, src)
        self.queue.insert(0, src)
        if guess and dest.parent.name == guess:
            self.accepted -= 1
        if self.pred:
            self._log(src.stem, guess, "UNDONE")
        self.show()

    def _log(self, crop_id, guess, final):
        new = not self.log.exists()
        with self.log.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["crop_id", "annotator", "predicted", "final", "accepted"])
            w.writerow([crop_id, self.person.name, guess, final, int(guess == final)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=pathlib.Path, default=pathlib.Path("work/gold"))
    a = ap.parse_args()

    labels = a.dir / "labels"
    people = sorted(d for d in labels.iterdir() if d.is_dir() and not d.name.startswith("."))
    if not people:
        raise SystemExit(f"no annotator folders in {labels} — run: python gold.py init")

    # classify.py writes a `pred` column, gold.py's answer_key.csv a `label` one.
    # Both are valid things to pre-fill a review from, so accept either.
    pred_file = a.dir / "predictions.csv"
    rows = list(csv.DictReader(pred_file.open())) if pred_file.exists() else []
    col = next((c for c in ("pred", "label") if rows and c in rows[0]), None)
    pred = {r["crop_id"]: r[col] for r in rows} if col else {}

    root = tk.Tk()
    root.title("review" if pred else "gold set (blind)")

    chooser = tk.Frame(root)
    chooser.pack(padx=40, pady=40)
    tk.Label(chooser, font=("", 18),
             text=f"who are you?\n{len(pred)} predictions loaded" if pred
                  else "who are you?\nblind labelling — no model answers shown").pack(pady=(0, 16))

    def pick(person):
        chooser.destroy()
        root.title(f"{'review' if pred else 'gold set'} — {person.name}")
        Sorter(root, person, pred, a.dir / "review_log.csv")

    for person in people:
        tk.Button(chooser, text=person.name, width=20, height=2,
                  command=lambda p=person: pick(p)).pack(pady=4)

    root.mainloop()


if __name__ == "__main__":
    main()
