"""Traffic-sign class labels and model-index mapping.

Single source of truth mapping the detector's numeric class ids to
human-meaningful sign labels, kept separate from detection/tracking so the
label set can evolve with the model without touching pipeline code.

TODO: populate with the deployed model's classes (e.g. speed-limit values,
stop, yield). Placeholder below.
"""
from __future__ import annotations

# model class id -> human label
CLASS_LABELS: dict[int, str] = {
    # 0: "speed_limit_30",
    # 1: "stop",
    # 2: "yield",
}


def label_for(class_id: int) -> str:
    """Human label for a detector class id (``"unknown"`` if unmapped)."""
    return CLASS_LABELS.get(class_id, "unknown")
