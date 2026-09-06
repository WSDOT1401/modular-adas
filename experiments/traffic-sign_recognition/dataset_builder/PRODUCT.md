# Product

Scope note: this file describes **dataset_builder** only, not the whole
`modular-adas` repo. The repo root holds unrelated surfaces (a Qt/QML instrument
cluster, a headless vision service), so a root-level PRODUCT.md would be
misleading. Point impeccable here:

```bash
IMPECCABLE_CONTEXT_DIR=experiments/traffic-sign_recognition/dataset_builder
```

## Register

product

## Users

One person: the engineer who owns this repo, curating their own dashcam footage
for a Thai traffic-sign detector. They run the app on `127.0.0.1`, alone, in
sessions of thirty to sixty minutes, switching between a laptop display and an
external monitor about equally. They are fluent in software and need no
hand-holding, but they are doing repetitive visual work and their attention is
the scarce resource, not their skill.

The job: look at a few hundred sampled road frames and decide, per frame,
**whether a traffic sign is visible at all**. Keep roughly forty out of ninety.
Hand the keepers to Roboflow or CVAT, which does the actual box drawing.

## Product Purpose

Footage is cheap and attention is expensive. A three-minute clip at 30 fps is
5,400 frames, and neighbouring frames are visually identical, so the value this
app adds is entirely in making the human pass fast and unambiguous. Success is
measured in frames-per-minute of confident judgement, and in never losing work.

The one hard physical constraint, measured on real footage: a Thai overhead
directional sign occupies about **70 px in a 2304 px-wide frame**, roughly 3% of
the frame width. Any layout that renders a frame smaller than about 440 CSS px
makes that sign under 14 px and the user's task impossible. Frame size is not a
matter of taste here. It is the product working or not working.

## Brand Personality

Quiet, exact, honest. The tool should read like a well-made instrument: it says
what it knows, admits what it does not, and never performs enthusiasm. No
celebration on download, no encouragement copy, no progress theatre. Numbers are
tabular and truthful; the frame number in a filename is a promise about which
moment of footage it came from.

## Anti-references

- SaaS dashboards. No hero metric, no icon-and-heading card grid, no gradient.
- Onboarding wizards, tours, tooltips that explain a button that should explain
  itself.
- Gamification: streaks, badges, "great job!", confetti.
- Photo-management apps that hide the image behind chrome. The frame is the
  content; everything else is scaffolding around it.
- Anything that implies multi-user, sharing, or the cloud. This binds to
  localhost and has no authentication, on purpose.

## Design Principles

1. **The frame is the interface.** Chrome earns its pixels or it goes. When
   space is contested, the image wins.
2. **Never make the user guess what they cannot see.** If a decision needs more
   resolution than the layout gives, the layout is wrong.
3. **Work is never lost.** Selections autosave on every click, and `progress.json`
   is tracked in git as the lab notebook.
4. **State is derived, not stored.** Progress icons are computed from the
   notebook on every load so they cannot drift out of sync with the truth.
5. **Say the awkward thing.** Dropped selections, missing caches, unreadable
   files, and failed saves are surfaced in plain words, not swallowed.

## Accessibility & Inclusion

Single known user, no assistive-tech requirement stated, so this is a
craft floor rather than a compliance target. Hold WCAG AA contrast on all text
and on the selected-frame indicator. Selection must be legible without relying
on hue alone, since a blue-on-photo border is exactly what a colour-vision
deficiency erases. Respect `prefers-reduced-motion`. Every mouse action needs a
keyboard path, and focus must be visible.
