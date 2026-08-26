"""Guards on the NCNN export artifacts — naming only, no GPU or training needed.

Ultralytics infers a model's format from its *filename*, so the export directory
name is load-bearing: get it wrong and the artifact is unloadable, which only
shows up when you try to run it on the Pi.
"""
import pytest

import train


def test_ncnn_dir_names_are_recognised_by_ultralytics():
    """Every export name must resolve to the 'ncnn' backend.

    An earlier version renamed exports to `best_ncnn_fp32` / `best_ncnn_fp16` to
    stop fp16 overwriting fp32. Both names are unloadable: AutoBackend._model_type
    substring-matches `_ncnn_model`, so it returned None and predict() raised
    "not a supported model format" on the Pi.
    """
    pytest.importorskip("ultralytics")
    from ultralytics.nn.autobackend import AutoBackend

    for tag in train.NCNN_VARIANTS:
        name = train.ncnn_dir_name(tag)
        assert "_ncnn_model" in name, f"{name} lacks the suffix ultralytics matches on"
        assert AutoBackend._model_type(f"/tmp/{name}") == "ncnn", name


def test_ncnn_dir_names_are_distinct():
    """fp32 and fp16 must not collide — every ncnn export writes to the same
    default directory, so they need distinct destinations."""
    names = {train.ncnn_dir_name(tag) for tag in train.NCNN_VARIANTS}
    assert len(names) == len(train.NCNN_VARIANTS)
