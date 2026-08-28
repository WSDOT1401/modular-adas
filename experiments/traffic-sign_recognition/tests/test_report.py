"""Unit tests for the comparison table — pure data, no runs or GPU needed."""
import pathlib

import report


def _run(name, imgsz, map50):
    return {"run": name, "imgsz": imgsz, "label_set": name.split("-")[0],
            "names": ["a"], "epochs_run": 100, "epochs_requested": 100,
            "map50": map50, "map": 0.7, "precision": 0.8, "recall": 0.8,
            "optimizer": "AdamW", "wall_seconds": 700,
            "dataset": {"split_at": 480, "official_split": False}}


def _pi_csv(path: pathlib.Path, throttled="0x0"):
    path.write_text(
        "run,variant,imgsz,status,total_ms,inference_ms,fps,throttled\n"
        f"4class-640,PyTorch,640,ok,206.5,201.5,4.8,{throttled}\n"
        f"4class-640,NCNN,640,ok,102.3,92.5,9.8,{throttled}\n"
        f"4class-640,NCNN-FP16,640,ok,100.4,91.4,10.0,{throttled}\n"
    )


def test_table_gains_latency_columns_when_benchmark_exists(tmp_path):
    _pi_csv(tmp_path / "pi_benchmark.csv")
    report.write_comparison([_run("4class-640", 640, 0.8668)], tmp_path / "comparison.md")
    text = (tmp_path / "comparison.md").read_text()
    header = next(l for l in text.splitlines() if l.startswith("| run |"))
    assert "Pi ms" in header and "Pi FPS" in header
    row = next(l for l in text.splitlines() if "`4class-640`" in l)
    assert "100.4" in row          # fastest variant's latency
    assert "10.0" in row           # its FPS
    assert "NCNN-FP16" in row      # and which format produced it


def test_latency_columns_are_dashes_without_a_benchmark(tmp_path):
    report.write_comparison([_run("4class-640", 640, 0.8668)], tmp_path / "comparison.md")
    text = (tmp_path / "comparison.md").read_text()
    assert "Pi ms" in text
    assert "no pi benchmark" in text.lower()


def test_throttled_benchmark_is_flagged(tmp_path):
    """0x50005 = under-voltage AND throttled right now; the numbers are a floor."""
    _pi_csv(tmp_path / "pi_benchmark.csv", throttled="0x50005")
    report.write_comparison([_run("4class-640", 640, 0.8668)], tmp_path / "comparison.md")
    text = (tmp_path / "comparison.md").read_text()
    assert "under-voltage" in text and "throttl" in text.lower()


def test_clean_benchmark_is_not_flagged(tmp_path):
    _pi_csv(tmp_path / "pi_benchmark.csv", throttled="0x0")
    report.write_comparison([_run("4class-640", 640, 0.8668)], tmp_path / "comparison.md")
    assert "under-voltage" not in (tmp_path / "comparison.md").read_text()
