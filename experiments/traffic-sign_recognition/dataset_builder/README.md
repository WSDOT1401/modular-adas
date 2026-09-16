# dataset_builder

A small local web app for turning dashcam footage into a curated set of frames
to label. Drop videos in, split them into stills every N seconds, click the ones
worth keeping, download a zip.

## Why this exists

The GTSDB models next door are trained on **German** signage. The car drives on
Thai roads, so we need Thai training data, and that starts with frames.

The bottleneck is not compute — it's *your attention*. A 3-minute clip at 30 fps
is 5,400 frames, and frames 1/30 s apart are visually identical, so keeping all
of them would produce a dataset that is mostly duplicates. This tool exists to
make the human part fast: sample at a sane interval, show you a grid, and get
your picks out of the building.

**It does not draw bounding boxes.** The zip goes to Roboflow / CVAT / Label
Studio, which already do annotation better than we could.

## Quickstart

```bash
CONDA=~/miniconda3/envs/w124-dash-env/bin
$CONDA/pip install -r requirements.txt      # flask; opencv is already there

cp /path/to/*.MP4 footage/                  # 1. drop footage in
$CONDA/python app.py                        # 2. run
open http://127.0.0.1:5001                  # 3. work
```

`mp4 · mov · avi · mkv · m4v · mts · m2ts · ts · webm`, case-insensitive.

## The workflow

```
footage/*.MP4
   │
   ├─ homepage        every clip, its state, and progress toward the target
   │                  tick the clips you don't want, Move to Trash
   │                  Active / Archived tabs to park clips you are done with
   │
   ├─ pick a clip  →  set an interval (default 2 s)  →  Extract
   │                  runs off-thread with a progress bar; a 20-minute
   │                  clip does not freeze the tab
   │
   ├─ contact sheet  click to pick · shift-click for a range · S/M/L sizes ·
   │                  enter or the corner button opens a frame at full
   │                  resolution · time ruler to jump · every click autosaves
   │
   └─ Download ZIP →  ~/Downloads  →  upload to your labelling tool
                      one clip from its own page, or tick several on the
                      homepage for a single combined zip
```

## Progress tracking

Each clip shows one of three states, **derived** from `progress.json` on every
page load — never stored, so it cannot drift out of sync with reality:

| icon | meaning | rule |
|:---:|---|---|
| ✗ | not started | nothing extracted yet |
| ◐ | in progress | extracted and/or selected, never downloaded |
| ✓ | done | downloaded at least once |

The ◐ state is the one that earns its keep: extract 600 frames from a long clip,
select 40, close the tab — the homepage tells you exactly where to pick back up,
and the selections are still there because they autosave on every click.

Open a ✓ clip and you get the grid with your previous picks already highlighted,
a history of every download with timestamps, and the button live again.

## What lands in ~/Downloads

```
2025_1230_004245_41frames.zip
├── 2025_1230_004245_f000300.jpg     ← full resolution, JPEG q95
├── 2025_1230_004245_f000360.jpg
├── ...
└── manifest.csv                     ← filename, source_video, frame_number,
                                       timestamp_s, width, height, interval_s
```

Images are flat at the root because every labelling tool flattens nested uploads
anyway. The frame number in the filename is the thread back to the exact moment
of footage a labelled image came from — `manifest.csv` carries the same
provenance in a form a script can read.

## Layout

```
app.py          Flask routes
extract.py      cv2 sampling — seek-based, records the frame it LANDED on
catalog.py      scans footage/, joins with progress, validates URL names
export.py       zip + manifest
progress.py     progress.json read/write, atomic
progress.json   the lab notebook (intended to be committed; run `git add` it)
footage/        your videos (gitignored)
workspace/      frame cache (gitignored, safe to delete, ~13 s to rebuild)
```

`progress.json` is meant to be tracked: it records which frames you curated out
of which footage, which is real dataset provenance, and `git log` becomes its
history. It is the only file here worth backing up. It is **not committed yet** —
it is not gitignored either, so `git add` it once you have curated something real.

## Notes

**Frame size.** A Thai overhead sign is about 70 px of a 2304 px-wide frame, so
a small thumbnail cannot answer "is there a sign here" at all: at the old 190 px
cell that sign rendered 6 px across. The sheet now defaults to 440 px cells with
S/M/L on the toolbar (remembered per browser), and any frame opens at full
source resolution with `enter` or the corner button. Arrow keys move, `space`
picks, `esc` returns to the sheet.

Thumbnails are 768 px wide to match. A cache extracted before that change is
upgraded in place, from the full-resolution JPEG already sitting next to it, the
first time the browser asks for each one. No re-extract, about 30 ms per frame.

**Downloading several clips at once.** Tick them on the homepage and press
Download ZIP: one flat archive, one `manifest.csv` covering the lot. Frame files
are already named `<clip stem>_f000123.jpg`, so frames from different clips
cannot collide -- unless two clips share a stem (`run.mp4` and `run.MOV`), which
already collides in the frame cache and is worth renaming. Ticked clips with
nothing selected are skipped, and each clip that contributes gets its own
download recorded, so the tick marks and `last download` column update as usual.

**Archiving a clip.** Tick its box and press Archive to move it to the Archived
tab; Restore brings it back. Nothing moves on disk -- it is one flag in
`progress.json` -- so the frames, the selections and the file itself survive, and
the frame count at the top of the page still includes archived clips.

**Deleting a clip.** Tick its box on the homepage and press Move to Trash. The
video goes to the macOS Trash, so a misclick is undone from Finder; its frame
cache and its `progress.json` row are removed outright, since both are derived.

**Interval.** Default 2 s. At 60 km/h that's ~33 m of road between frames — far
enough apart to be genuinely different images. Stopped at a red light they will
be near-identical no matter what interval you pick, so skip those stretches.

**Re-extracting** at a different interval changes which frames exist. Selections
that survive are kept, the rest are dropped, and the app tells you how many.

**Seeking.** Frames are located by seeking, so cost scales with frames *wanted*,
not clip *length* — 90 frames out of a 3-minute clip takes ~13 s, and a 20-minute
clip costs barely more. Seeking is frame-accurate on well-formed MP4 (verified: 0
mismatches over 8 probes on real footage), but not every dashcam writes
well-formed MP4, so the recorded frame number is the one we *landed* on, never
the one we asked for. A filename claiming `_f000300` is always telling the truth.
Clips with no usable fps or frame count fall back to walking the file by
timestamp — slower, but it works on anything OpenCV can decode.

**Two things visible in the real footage** that will affect the dataset, neither
handled here:

- The camera burns a **timestamp overlay** into every frame.
- The **car hood and dashboard reflection** occupy roughly the bottom quarter.

Both are constant across every frame from the same camera, so a detector can
learn to ignore them — but cropping the bottom of the frame would remove both at
once and give the model more useful pixels. Worth deciding before labelling
starts, because it is expensive to change afterwards.

**Port 5001, not 5000.** macOS AirPlay Receiver listens on `[::1]:5000`, so a
browser that resolves `localhost` to IPv6 reaches AirPlay and shows `403
Forbidden` instead of this app. Override with `--port` if 5001 is busy too.

**Security.** Binds to `127.0.0.1` only. It reads and writes files on your
machine with no authentication — do not expose it to a network.
