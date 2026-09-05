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
open http://127.0.0.1:5000                  # 3. work
```

`mp4 · mov · avi · mkv · m4v · mts · m2ts · ts · webm`, case-insensitive.

## The workflow

```
footage/*.MP4
   │
   ├─ homepage        every clip, its state, and progress toward the target
   │
   ├─ pick a clip  →  set an interval (default 2 s)  →  Extract
   │                  runs off-thread with a progress bar; a 20-minute
   │                  clip does not freeze the tab
   │
   ├─ grid           click to toggle · shift-click for a range · time ruler
   │                  to jump · every click autosaves
   │
   └─ Download ZIP →  ~/Downloads  →  upload to your labelling tool
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
progress.json   TRACKED IN GIT — the lab notebook
footage/        your videos (gitignored)
workspace/      frame cache (gitignored, safe to delete, ~13 s to rebuild)
```

`progress.json` is tracked on purpose: it records which frames you curated out of
which footage, which is real dataset provenance, and `git log` becomes its
history. It is the only file here worth backing up.

## Notes

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

**Security.** Binds to `127.0.0.1` only. It reads and writes files on your
machine with no authentication — do not expose it to a network.
