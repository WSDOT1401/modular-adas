# thai-traffic-sign-labs

Hand-annotated Thai traffic signs from dashcam footage. 330 frames, 419 boxes,
3 supercategories (`Regulatory` / `Warning` / `Information`), drawn from **30
recordings**.

`datasets/` is gitignored (241 MB); `extractor.py` merges the CVAT session
exports that produce it.

## ⚠️ Post-export edits live here, not in CVAT

`qa/fix_labels.py` was applied to the current export. **A fresh CVAT export will
silently undo it.** Re-run the script after any re-export, or make the same
changes in CVAT and delete the script.

It does two things (both idempotent, both patch the YOLO labels *and* the COCO
json so the two stay in agreement):

* **Deletes 8 boxes** covering only the red header strip of red-over-yellow Thai
  roadside notice boards. They are not official signs, and boxing just the strip
  teaches "red horizontal rectangle = Regulatory sign" — which fires on every
  shop banner in Thailand.
* **Reclassifies 1 box** in `2026_0912_012925_f002850`, a blue circular mandatory
  sign, from `Information` to `Regulatory`.

## Known limitation: sign-border convention

Box edges are not consistent — some include the backing plate, some are tight to
the sign face, some clip into it. Accepted deliberately: the noise is constant
across every run, so it shifts absolute mAP down without changing the shape of a
data-scaling curve. It costs mAP50-95 more than mAP50. Fix it before chasing
absolute accuracy, not before.

## Audit

```bash
CONDA=~/miniconda3/envs/w124-dash-env/bin

$CONDA/python qa/audit.py    # structure, per-class counts, box geometry, near-dupes
$CONDA/python qa/audit2.py   # COCO<->YOLO agreement, clip topology, empty frames
$CONDA/python qa/viz.py      # contact sheets -> qa/out/
```

Current expected state: 419 boxes (Regulatory 131 / Warning 139 /
Information 149), 330 image+label pairs, 108 background frames, 0 malformed.
`audit2.py` reports 6 geometry deltas — those are CVAT `rotation` annotations,
where the YOLO export stores the axis-aligned hull and COCO the unrotated rect.
Pre-existing and expected.

## Training

The split and the Colab notebook live one level up, in
`experiments/traffic-sign_recognition/`: `prepare_thai.py` (clip-grouped
70/20/10 split), `thai_splits.json` (the committed split), and
`notebooks/colab_thai_signs.ipynb`.
