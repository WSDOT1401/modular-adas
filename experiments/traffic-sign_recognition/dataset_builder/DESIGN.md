# Design

The visual system for **dataset_builder**. Strategy and users live in
[PRODUCT.md](PRODUCT.md). Everything here is implemented in
[`static/app.css`](static/app.css); if the two disagree, the CSS is right and
this file is stale.

## The one measurement that shapes everything

A Thai overhead directional sign occupies about **70 px in a 2304 px-wide
frame**, roughly 3% of the width. That number sets the layout:

| rendered cell | sign renders at | verdict |
|---|---|---|
| 190 px (the old grid) | 6 px | impossible |
| 320 px (`S`) | 10 px | overview only |
| 440 px (`M`, default) | 13 px | the floor for "is a sign there" |
| 640 px (`L`) | 19 px | comfortable |
| 2304 px (viewer) | 70 px | readable |

Frame size is not a taste question here. Below roughly 440 px the product does
not work.

## Theme

Two surfaces, deliberately different.

The **homepage** is a table you read, so it is light and capped at 1280 px.

The **frames page** is a contact sheet you judge, so it runs the full viewport
and the frames sit in a dark well. The scene: one person at a desk in the
evening, deciding whether a sign is present in a few hundred road frames that
each contain both a bright sky and a black car hood. A light surround makes the
hood read muddy and the sky read blown out. The chrome stays light so the tool
still feels like the same application.

## Color

Strategy: **Restrained.** Tinted neutrals plus one accent, used only for the
primary action, the current selection, and state. Never for decoration.

All values are OKLCH. Neutrals carry a small chroma at the accent hue (262) so
the greys read as a family; nothing is pure black or pure white.

| token | value | role |
|---|---|---|
| `--ink` | `oklch(24% 0.018 262)` | body text |
| `--muted` | `oklch(55% 0.020 262)` | secondary text |
| `--line` | `oklch(91% 0.008 262)` | borders |
| `--line-2` | `oklch(95% 0.006 262)` | hairlines, tracks |
| `--bg` | `oklch(97.5% 0.004 262)` | page |
| `--card` | `oklch(99.5% 0.002 262)` | panels |
| `--accent` | `oklch(55% 0.190 258)` | primary action, selection |
| `--accent-2` | `oklch(48% 0.185 258)` | accent hover |
| `--ok` | `oklch(52% 0.130 150)` | done |
| `--warn` | `oklch(50% 0.150 42)` | caution |
| `--danger` | `oklch(52% 0.190 27)` | failure |
| `--well` | `oklch(26% 0.012 262)` | the viewing surface |
| `--well-line` | `oklch(35% 0.014 262)` | borders inside the well |
| `--well-ink` | `oklch(80% 0.010 262)` | text on the well |
| `--well-dim` | `oklch(62% 0.012 262)` | secondary text on the well |

Every text pair measures at or above WCAG AA (4.5:1); the tightest is the ruler
label at 5.67:1.

**Selection is signalled three ways at once**: the outline goes 1 px to 3 px, a
badge with a check appears, and the colour changes. A blue border over a
photograph is exactly what a colour-vision deficiency erases, so shape and
weight carry the signal too.

## Typography

One family, the system stack. No display face, no web font, no loading strategy
to get wrong.

| step | size | use |
|---|---|---|
| 30 px / 650 | `.big` | the one number on the homepage |
| 17 px / 600 | `.clip-title` | clip name |
| 14 px | body | everything |
| 12 px | `.small` | secondary |
| 11 px | `.stamp .fno`, `kbd` | stamps and keys |
| 10 px | `.ruler button` | the scrub strip |

Ratio is about 1.2, on the tight side, because this UI has many labels and
exaggerated contrast would only add noise. All numbers use
`font-variant-numeric: tabular-nums` so timecodes and counts do not jitter.

## Space

Scale: 4 / 8 / 12 / 14 / 16 / 20 / 24. Radii: 6 px controls, 10 px panels,
14 px the well.

The frames page spends its vertical budget deliberately. Title and facts share
one line. The interval control folds into a disclosure once frames exist,
because setting it is a once-per-clip act. Total chrome above the first frame
is about 215 px, which leaves two full rows visible on a 900 px laptop.

## Components

- **Cell.** A figure holding one image and two sibling buttons: the whole frame
  picks it, a corner button enlarges it. Buttons cannot nest, and a div with
  click handlers gives the keyboard nothing. `aspect-ratio` is set from the real
  frame dimensions so lazy images reserve their box instead of shifting the page.
- **Size control.** Three steps, not a slider. What matters is whether a sign is
  visible, which is a threshold rather than a continuum. Remembered in
  `localStorage`, because the right size depends on which screen you are at.
- **Ruler.** A scrub strip, not a row of buttons. Hidden below 640 px, where
  eleven 10 px targets stop being a control.
- **Viewer.** Full source resolution, opaque background, arrow keys to move,
  space to pick, Esc back to the sheet with focus on the frame you were looking
  at rather than the one you came in from.

## Motion

`--t: 170ms` with `--ease: cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-expo).
Motion only conveys state: outline colour, badge appearance, hover affordance.
Nothing animates a layout property, nothing choreographs on page load, and
`prefers-reduced-motion` collapses every duration to 1 ms.

## Bans observed

No side-stripe borders, no gradient text, no glassmorphism, no hero-metric
block, no decorative card grid, no em dashes in UI copy.
