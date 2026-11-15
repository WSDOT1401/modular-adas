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
``adas/vision/signs/classes.py``, which runs on the Pi.
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
# (Exception, 2026-11-15: seven names appended inside their own parent rather
# than at the end -- chevron/merge/railway_crossing/crossroads under Warning,
# no_pedestrians/mandatory_direction/height_limit under Regulatory -- so every
# name after each insertion shifts. Safe only because nothing has been trained
# on thai_fine yet; M1 collapses all of these to a single class. M2 trains on
# this order, so from here it really is frozen.
#
# All seven came out of other_regulatory/other_warning, never out of a real
# class: splitting a catch-all is free, merging two real classes is not.)
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
        # The blue REGULATORY sign showing a white bus: this lane or road is
        # reserved for them. NOT the bus-stop board at the kerb, which is
        # roadside furniture and gets its box deleted -- see `information`.
        "reserved_for_bus",
        # Split out of other_regulatory on 2026-11-15, same reasoning as
        # `chevron`: each was a visually unmistakable block inside the bucket,
        # and a bucket the model cannot tell apart from itself is the one thing
        # background-splitting says not to hand it. Counts are small on purpose
        # -- a group under ~6 crops was left in the catch-all, because another
        # name costs a reviewer a decision on every 30 px crop they see.
        "no_pedestrians",      # walking figure, red ring, slash
        "mandatory_direction", # black arrow in a RED ring -- not the blue
                               # turn_left/turn_right, which command a turn
        "height_limit",        # "5.00 ม." between two triangles
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
        # Yellow board, one fat black arrow, planted in a row around the outside
        # of a bend. Split out of other_warning on 2026-11-15 because it was
        # roughly half that bucket -- 229 crops of one drawing sitting in the
        # catch-all, which is the thing a catch-all is supposed not to be. It is
        # also the nearest neighbour to left_curve/right_curve (yellow, black,
        # directional), so leaving it unnamed put 229 distractors against their
        # 19 real crops. One class, not chevron_left/right: nothing downstream
        # reads the direction, and asking a reviewer to call left-vs-right on a
        # 30 px crop buys noise.
        "chevron",
        "merge",            # Y-shaped arrow, two lanes becoming one
        "railway_crossing", # the picket-fence pictogram
        "crossroads",       # "+", and the plain "T" side-road variant
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
        #
        # THE RULE, written down 2026-11-16 because not having it was costing
        # real labels. `information` is a GUIDE SIGN ERECTED BY THE ROAD
        # AUTHORITY: place names, distances, direction arrows, lane diagrams,
        # facility boards. Anything else rectangular with text on it is NOT a
        # sign and its box is deleted -- shop fronts, billboards, posters, and
        # bus-stop boards at the kerb.
        #
        # An appearance test cannot settle this, which is why one was not
        # enough: a billboard really is "a large board with text", and the
        # classifier calls one `information` at 0.94 for exactly that reason.
        # The test is who put it there and whether it helps you drive.
        #
        # It matters because `information` is one of the 13 the dash SHOWS.
        # Label a bus shelter `information` and the screen speaks at every bus
        # stop -- not a quiet error, a driver-visible one. Of M2's `not_a_sign`
        # mistakes, 10 went to `information` and 9 to `reserved_for_bus`: over
        # half of them landed on this one boundary, because the labels said
        # both answers. See JOURNAL 2026-11-16.
        "information",
    ),
}

THAI_FINE_NAMES = [n for group in THAI_FINE_BY_PARENT.values() for n in group]

# The 13 M2 actually SHOWS on the dash. The other 15 are helper classes: a right
# answer the driver never sees. Training on a name per sign family rather than
# one "other" bucket is Background Splitting (Mullapudi et al., CVPR 2021) --
# a catch-all is the hardest kind of class to learn, and we already had the
# labels. See JOURNAL 2026-11-15.
#
# This list is also what the scoreboard averages over, so it is what M2's
# train/val split is built to cover: a class with no val crops is a blank cell
# in the presentation, which is the one thing a split can control.
THAI_FINE_DISPLAYED: tuple[str, ...] = (
    "stop", "no_left_turn", "no_right_turn", "no_right_u_turn", "speed_limit",
    "keep_left", "keep_right", "keep_left_or_right", "turn_left", "turn_right",
    "left_curve", "right_curve", "information",
)
assert set(THAI_FINE_DISPLAYED) <= set(THAI_FINE_NAMES)

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
