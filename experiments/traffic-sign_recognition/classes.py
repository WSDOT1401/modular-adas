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
LABEL_SETS = GTSDB_LABEL_SETS + ("thai3", "thai_fine")

# Thai supercategories, in output-index order. This IS the class order in
# data.yaml and in every exported model — reordering it invalidates weights.
THAI3_NAMES = ["Regulatory", "Warning", "Information"]


# ---------------------------------------------------------------- thai_fine --
# The fine-grained target: a STOP sign is ``stop``, not ``Regulatory``.
#
# Grouped by the thai3 supercategory it lives under, because the annotation
# pipeline shows a VLM only the candidates for a crop's already-known coarse
# class — that is what makes the decision ~23-way instead of ~30-way. Flattened
# in THAI_FINE_NAMES order, so each parent owns a contiguous block of indices.
#
# As with THAI3_NAMES: this order IS the class order in data.yaml and in every
# exported model. Append, never reorder.
#
# (Exception, 2026-09-23: reserved_for_pedestrians -> pedestrian_crossing, moved
# Regulatory -> Warning. Indices shifted, which is safe only because nothing has
# been trained on thai_fine yet. From here on, append.)
#
# Trimmed 2026-10-03: give_way, no_entry, no_left_u_turn, roundabout,
# end_of_restriction and t_junction drew zero examples across 35 clips, so they
# were cut rather than shipped as classes that can never be scored. Their crops
# fall to the matching other_* bucket, so no footage is lost. keep_left and
# keep_right are also empty so far but were kept deliberately.
#
# ``other_*`` means "clearly a sign, legible, just not on this list" — never
# "too blurry to tell". Conflating those teaches the model that a grey smudge is
# an ``other_*`` sign. Unreadable crops are dropped, not labelled.
THAI_FINE_BY_PARENT: dict[str, tuple[str, ...]] = {
    "Regulatory": (
        "stop",
        "no_left_turn",
        "no_right_turn",
        "no_right_u_turn",
        "no_stopping_parking",
        # One class for every posted limit, the number deliberately not split
        # out. Per-value classes (30/50/60/80/...) each drew a handful of
        # examples from 35 clips -- the signs are identical but for the digits,
        # so splitting them spent the data on eight thin classes instead of one
        # solid one. Read the number as an attribute once detection is good
        # enough to be worth it.
        "speed_limit",
        "keep_left",
        "keep_right",
        "keep_left_or_right",
        "turn_left",
        "turn_right",
        "reserved_for_bus",
        "other_regulatory",
    ),
    "Warning": (
        "left_curve",
        "right_curve",
        "t_junction_left",
        "t_junction_right",
        # Yellow-green diamond with a walking figure: "people cross here".
        # NOT the blue circle "pedestrians only" sign — different shape,
        # different supercategory. It is the single most common sign in
        # this footage (32 of the first 73 gold crops).
        "pedestrian_crossing",
        "other_warning",
    ),
    # Thai Information signs are mostly text and direction boards with no fixed
    # iconography, so there is nothing stable to enumerate. Kept as one bucket
    # deliberately — say so when asked why it is not subdivided like the others.
    "Information": (
        # Blue square, white U-turn arrow, usually with a supplementary plate
        # ("under the bridge", "100 m"). Square, not circular, so it points at a
        # U-turn facility rather than commanding one — hence Information, not
        # Regulatory. Distinct from no_left_u_turn / no_right_u_turn, which
        # prohibit the manoeuvre. 6 of the first 133 gold crops.
        "u_turn",
        # Catch-all, and deliberately the only other entry: Thai information
        # signs are mostly text and direction boards with no fixed iconography,
        # so there is nothing stable to enumerate. Keep it last.
        "information",
    ),
}

THAI_FINE_NAMES = [n for group in THAI_FINE_BY_PARENT.values() for n in group]

# fine class name -> its thai3 parent, for the VLM prompt and for collapsing a
# fine prediction back to the coarse label.
THAI_FINE_PARENT: dict[str, str] = {
    name: parent for parent, group in THAI_FINE_BY_PARENT.items() for name in group
}


def _thai_fine() -> tuple[list[str], dict[int, int]]:
    """Identity mapping: annotations are authored directly in these indices."""
    return list(THAI_FINE_NAMES), {i: i for i in range(len(THAI_FINE_NAMES))}


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


_BUILDERS = {
    "4class": _four_class,
    "1class": _one_class,
    "thai3": _thai3,
    "thai_fine": _thai_fine,
}


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
