"""Label sets — the single source of truth for what we train to detect.

GTSDB ships 43 sign classes but only ~600 training images, so several classes
appear fewer than ten times. Training on all 43 yields near-zero mAP on the long
tail, so we train two coarser targets instead and compare them:

* ``4class`` — the canonical GTSDB *detection* grouping (prohibitory / danger /
  mandatory / other). Enough examples per bucket to produce meaningful metrics.
* ``1class`` — "is there a sign here at all", the upper bound on localisation
  quality and the front half of a detect-then-classify design.

``thai3`` is the separate hand-annotated Thai dashcam set (see
``thai-traffic-sign-labs/``), which is exported from CVAT already numbered
0/1/2 — so unlike the GTSDB sets its mapping is the identity.

Deliberately dependency-free: this module is what will later seed
``services/vision/signs/classes.py``, which runs on the Pi.
"""
from __future__ import annotations

# GTSDB/GTSRB define ids 0..42.
GTSDB_NUM_CLASSES = 43

# Canonical GTSDB detection grouping, in output-index order: the key order here
# *is* the class order in data.yaml, so don't reorder without retraining.
SUPER_CLASS_IDS: dict[str, tuple[int, ...]] = {
    "prohibitory": (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 15, 16),
    "danger": (11, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31),
    "mandatory": (33, 34, 35, 36, 37, 38, 39, 40),
    "other": (6, 12, 13, 14, 17, 32, 41, 42),
}

# Sets whose mapping keys are GTSDB ids, so they must cover all 43.
GTSDB_LABEL_SETS = ("4class", "1class")
LABEL_SETS = GTSDB_LABEL_SETS + ("thai3",)

# Thai supercategories, in output-index order. This IS the class order in
# data.yaml and in every exported model — reordering it invalidates weights.
THAI3_NAMES = ["Regulatory", "Warning", "Information"]


def _four_class() -> tuple[list[str], dict[int, int]]:
    names = list(SUPER_CLASS_IDS)
    mapping = {
        gtsdb_id: idx
        for idx, bucket in enumerate(SUPER_CLASS_IDS.values())
        for gtsdb_id in bucket
    }
    return names, mapping


def _one_class() -> tuple[list[str], dict[int, int]]:
    return ["sign"], {gtsdb_id: 0 for gtsdb_id in range(GTSDB_NUM_CLASSES)}


def _thai3() -> tuple[list[str], dict[int, int]]:
    """The Thai export is already 0/1/2, so nothing needs remapping."""
    return list(THAI3_NAMES), {i: i for i in range(len(THAI3_NAMES))}


_BUILDERS = {"4class": _four_class, "1class": _one_class, "thai3": _thai3}


def label_set(name: str) -> tuple[list[str], dict[int, int]]:
    """Return ``(class_names, {source_class_id: train_class_index})`` for ``name``.

    ``class_names`` is ordered to match the training indices, i.e. it drops
    straight into ``data.yaml``'s ``names``. Raises ``KeyError`` on an unknown
    label set rather than silently guessing.
    """
    try:
        builder = _BUILDERS[name]
    except KeyError:
        raise KeyError(f"unknown label set {name!r}; expected one of {LABEL_SETS}") from None
    return builder()
