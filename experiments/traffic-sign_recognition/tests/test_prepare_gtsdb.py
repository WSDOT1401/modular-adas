"""Unit tests for the GTSDB -> YOLO converter, on a synthetic dataset.

Builds a miniature GTSDB in tmp_path (hand-written P6 PPMs + gt.txt) so the real
1.6 GB download is never needed. Covers the parts that silently corrupt a
training run when wrong: coordinate normalisation, class remapping, background
negatives, degenerate boxes, and the official 600/300 split boundary.
"""
import pathlib

import pytest
import yaml

from prepare_gtsdb import prepare

# (index, [(left, top, right, bottom, gtsdb_class_id), ...])
#  W=100 H=50 for every image, so expected normalised values are easy to read.
IMG_W, IMG_H = 100, 50
FIXTURE = {
    0:   [(10, 10, 30, 30, 1)],                              # -> prohibitory
    1:   [],                                                 # negative (absent from gt.txt)
    2:   [(40, 10, 40, 30, 11), (50, 10, 70, 30, 11)],       # first is degenerate -> dropped
    599: [(10, 10, 30, 30, 33)],                             # last train index
    600: [(10, 10, 30, 30, 6)],                              # first val index
}


def _write_ppm(path: pathlib.Path, w: int, h: int) -> None:
    """Minimal binary PPM (P6) so cv2 has something real to decode."""
    body = bytes((i * 7) % 256 for i in range(w * h * 3))
    path.write_bytes(b"P6\n%d %d\n255\n" % (w, h) + body)


@pytest.fixture
def gtsdb_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A synthetic GTSDB, nested one level to exercise gt.txt auto-discovery."""
    root = tmp_path / "kaggle_input" / "FullIJCNN2013"
    root.mkdir(parents=True)
    lines = []
    for idx, boxes in FIXTURE.items():
        _write_ppm(root / f"{idx:05d}.ppm", IMG_W, IMG_H)
        for left, top, right, bottom, cid in boxes:
            lines.append(f"{idx:05d}.ppm;{left};{top};{right};{bottom};{cid}")
    (root / "gt.txt").write_text("\n".join(lines) + "\n")
    return root.parent          # hand back the *parent* — discovery must find gt.txt


def _labels(out: pathlib.Path, label_set: str, split: str, idx: int) -> list[list[str]]:
    txt = out / f"gtsdb-{label_set}" / "labels" / split / f"{idx:05d}.txt"
    assert txt.exists(), f"{txt} missing"
    return [ln.split() for ln in txt.read_text().split("\n") if ln.strip()]


def test_known_box_normalises_correctly(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    prepare(gtsdb_root, out, "4class")
    (row,) = _labels(out, "4class", "train", 0)
    cls, cx, cy, w, h = row
    # box (10,10)-(30,30) in a 100x50 image
    assert cls == "0"
    assert float(cx) == pytest.approx(20 / IMG_W)      # 0.20
    assert float(cy) == pytest.approx(20 / IMG_H)      # 0.40
    assert float(w) == pytest.approx(20 / IMG_W)       # 0.20
    assert float(h) == pytest.approx(20 / IMG_H)       # 0.40


def test_4class_remapping(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    prepare(gtsdb_root, out, "4class")
    assert _labels(out, "4class", "train", 0)[0][0] == "0"      # id 1  -> prohibitory
    assert _labels(out, "4class", "train", 2)[0][0] == "1"      # id 11 -> danger
    assert _labels(out, "4class", "train", 599)[0][0] == "2"    # id 33 -> mandatory
    assert _labels(out, "4class", "val", 600)[0][0] == "3"      # id 6  -> other


def test_1class_collapses_every_id(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    prepare(gtsdb_root, out, "1class")
    for split, idx in (("train", 0), ("train", 2), ("train", 599), ("val", 600)):
        assert _labels(out, "1class", split, idx)[0][0] == "0"


def test_image_without_annotations_gets_empty_label_file(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    summary = prepare(gtsdb_root, out, "4class")
    txt = out / "gtsdb-4class" / "labels" / "train" / "00001.txt"
    assert txt.exists(), "background images need an empty .txt, not a missing one"
    assert txt.read_text().strip() == ""
    assert summary["splits"]["train"]["negatives"] == 1


def test_degenerate_box_is_dropped(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    summary = prepare(gtsdb_root, out, "4class")
    rows = _labels(out, "4class", "train", 2)
    assert len(rows) == 1, "zero-width box should not survive"
    assert summary["dropped"] == 1


def test_official_600_split_boundary(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    summary = prepare(gtsdb_root, out, "4class")
    imgs = out / "_images"
    assert (imgs / "train" / "00599.png").exists()
    assert (imgs / "val" / "00600.png").exists()
    assert not (imgs / "val" / "00599.png").exists()
    assert summary["splits"]["train"]["images"] == 4
    assert summary["splits"]["val"]["images"] == 1


def test_data_yaml_names_match_label_set(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    for name, expected in (("4class", 4), ("1class", 1)):
        summary = prepare(gtsdb_root, out, name)
        cfg = yaml.safe_load(pathlib.Path(summary["data_yaml"]).read_text())
        assert len(cfg["names"]) == expected
        assert cfg["train"] == "images/train" and cfg["val"] == "images/val"


def test_images_are_hardlinked_not_copied(gtsdb_root, tmp_path):
    """Both label sets share one set of pixels — hardlinks, so no extra disk."""
    out = tmp_path / "ds"
    prepare(gtsdb_root, out, "4class")
    prepare(gtsdb_root, out, "1class")
    a = out / "gtsdb-4class" / "images" / "train" / "00000.png"
    b = out / "gtsdb-1class" / "images" / "train" / "00000.png"
    cache = out / "_images" / "train" / "00000.png"
    assert a.stat().st_ino == b.stat().st_ino == cache.stat().st_ino
    # NOT symlinks: check_det_dataset resolves those, which reroutes the split
    # path to _images/ and makes img2label_paths look for a nonexistent
    # _labels/ — every image then loads as background and training learns
    # nothing, silently. See test_ultralytics_actually_finds_the_labels.
    assert not a.is_symlink() and not b.is_symlink()


def test_conversion_is_idempotent(gtsdb_root, tmp_path):
    out = tmp_path / "ds"
    first = prepare(gtsdb_root, out, "4class")
    stamp = (out / "_images" / "train" / "00000.png").stat().st_mtime_ns
    second = prepare(gtsdb_root, out, "4class")
    assert first["splits"] == second["splits"]
    assert (out / "_images" / "train" / "00000.png").stat().st_mtime_ns == stamp
    assert second["converted"] == 0, "cached PNGs should not be re-encoded"


def test_missing_gt_txt_is_a_clear_error(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="gt.txt"):
        prepare(empty, tmp_path / "ds", "4class")


def test_ultralytics_actually_finds_the_labels(gtsdb_root, tmp_path):
    """End-to-end guard: let ultralytics itself load the dataset.

    The unit tests above all passed against an earlier symlinked-directory
    layout that ultralytics silently read as 100% background images. Only
    ultralytics' own loader catches that, so it is worth the dependency.
    """
    pytest.importorskip("ultralytics")
    from ultralytics.data.dataset import YOLODataset
    from ultralytics.data.utils import check_det_dataset

    out = tmp_path / "ds"
    summary = prepare(gtsdb_root, out, "4class")
    data = check_det_dataset(summary["data_yaml"])
    assert data["nc"] == 4

    found = {}
    for split in ("train", "val"):
        ds = YOLODataset(img_path=str(data[split]), imgsz=640, data=data, augment=False)
        found[split] = sum(len(lbl["bboxes"]) for lbl in ds.labels)
    # fixture: train 00000/00002/00599 = 3 boxes (one degenerate dropped), val 00600 = 1
    assert found == {"train": 3, "val": 1}


def test_empty_split_fails_loudly(tmp_path):
    """An all-train dataset must fail at conversion, not 10 min into training.

    Some GTSDB redistributions ship train and test as separate directories, each
    with its own gt.txt and each numbered from 00000 — so the `index < 600` rule
    puts everything in train. Left unchecked, ultralytics later dies on
    "No images found in .../images/val", which says nothing about the real cause.
    """
    root = tmp_path / "train_only"
    root.mkdir()
    for idx in range(3):                          # every index < 600
        _write_ppm(root / f"{idx:05d}.ppm", IMG_W, IMG_H)
    (root / "gt.txt").write_text("00000.ppm;10;10;30;30;1\n")

    with pytest.raises(ValueError) as excinfo:
        prepare(root, tmp_path / "ds", "4class")
    message = str(excinfo.value)
    assert "val" in message                       # names the empty split
    assert "00000" in message and "00002" in message   # shows the index range
    assert "600" in message                       # explains the split rule


def test_multiple_gt_txt_files_are_reported(tmp_path, capsys):
    """Two gt.txt dirs means we silently used one — say so, don't hide it."""
    root = tmp_path / "split_layout"
    for sub, start in (("TrainIJCNN2013", 0), ("TestIJCNN2013", 600)):
        d = root / sub
        d.mkdir(parents=True)
        for offset in range(2):
            _write_ppm(d / f"{start + offset:05d}.ppm", IMG_W, IMG_H)
        (d / "gt.txt").write_text(f"{start:05d}.ppm;10;10;30;30;1\n")

    with pytest.raises(ValueError):        # only one dir is read -> a split is empty
        prepare(root, tmp_path / "ds", "4class")
    out = capsys.readouterr().out
    assert "TrainIJCNN2013" in out and "TestIJCNN2013" in out, \
        "both gt.txt directories must be named in the output"


@pytest.fixture
def split_layout_root(tmp_path):
    """GTSDB shipped as TrainIJCNN2013/ + TestIJCNN2013/, both numbered from 0.

    This is the layout that breaks the index rule: the test images restart at
    00000, so `index < 600` calls all of them train.
    """
    root = tmp_path / "split_layout"
    for sub, ids, cid in (("TrainIJCNN2013", (0, 1, 2), 1), ("TestIJCNN2013", (0, 1), 33)):
        d = root / sub
        d.mkdir(parents=True)
        lines = []
        for idx in ids:
            _write_ppm(d / f"{idx:05d}.ppm", IMG_W, IMG_H)
            lines.append(f"{idx:05d}.ppm;10;10;30;30;{cid}")
        (d / "gt.txt").write_text("\n".join(lines) + "\n")
    return root


def test_explicit_dirs_split_by_directory_not_index(split_layout_root, tmp_path):
    out = tmp_path / "ds"
    summary = prepare(
        split_layout_root, out, "4class",
        train_dir="TrainIJCNN2013", val_dir="TestIJCNN2013",
    )
    assert summary["splits"]["train"]["images"] == 3
    assert summary["splits"]["val"]["images"] == 2
    # both dirs number from 00000 — they must not collide, and each keeps its class
    assert _labels(out, "4class", "train", 0)[0][0] == "0"    # id 1  -> prohibitory
    assert _labels(out, "4class", "val", 0)[0][0] == "2"      # id 33 -> mandatory


def test_explicit_dirs_accept_absolute_paths(split_layout_root, tmp_path):
    summary = prepare(
        split_layout_root, tmp_path / "ds", "4class",
        train_dir=split_layout_root / "TrainIJCNN2013",
        val_dir=split_layout_root / "TestIJCNN2013",
    )
    assert summary["splits"]["val"]["images"] == 2


def test_one_explicit_dir_without_the_other_is_rejected(split_layout_root, tmp_path):
    with pytest.raises(ValueError, match="together"):
        prepare(split_layout_root, tmp_path / "ds", "4class", train_dir="TrainIJCNN2013")


def test_explicit_dir_without_gt_txt_is_a_clear_error(split_layout_root, tmp_path):
    (split_layout_root / "Empty").mkdir()
    with pytest.raises(FileNotFoundError, match="gt.txt"):
        prepare(split_layout_root, tmp_path / "ds", "4class",
                train_dir="TrainIJCNN2013", val_dir="Empty")


def test_split_layout_survives_ultralytics(split_layout_root, tmp_path):
    """The layout that caused the original bug must now load end-to-end."""
    pytest.importorskip("ultralytics")
    from ultralytics.data.dataset import YOLODataset
    from ultralytics.data.utils import check_det_dataset

    summary = prepare(split_layout_root, tmp_path / "ds", "4class",
                      train_dir="TrainIJCNN2013", val_dir="TestIJCNN2013")
    data = check_det_dataset(summary["data_yaml"])
    found = {
        split: sum(len(l["bboxes"]) for l in
                   YOLODataset(img_path=str(data[split]), imgsz=640,
                               data=data, augment=False).labels)
        for split in ("train", "val")
    }
    assert found == {"train": 3, "val": 2}


def _write_png(path: pathlib.Path, w: int, h: int) -> None:
    from PIL import Image
    Image.new("RGB", (w, h), (40, 90, 140)).save(path)


def test_accepts_datasets_already_converted_to_png(tmp_path):
    """Some GTSDB mirrors ship PNG/JPG instead of PPM, keeping gt.txt as-is.

    The PPM->PNG step exists only because ultralytics cannot read PPM. If a
    mirror already did it, use those files directly rather than refusing.
    """
    root = tmp_path / "png_mirror"
    root.mkdir()
    lines = []
    for idx in (0, 1, 600):
        _write_png(root / f"{idx:05d}.png", IMG_W, IMG_H)
        # gt.txt still names .ppm even though the files are .png
        lines.append(f"{idx:05d}.ppm;10;10;30;30;1")
    (root / "gt.txt").write_text("\n".join(lines) + "\n")

    out = tmp_path / "ds"
    summary = prepare(root, out, "4class")
    assert summary["splits"]["train"]["images"] == 2
    assert summary["splits"]["val"]["images"] == 1
    assert summary["converted"] == 0, "already-readable images must not be re-encoded"
    # annotations matched by stem, so the .ppm/.png mismatch is harmless
    assert _labels(out, "4class", "train", 0)[0][0] == "0"
    assert _labels(out, "4class", "val", 600)[0][0] == "0"


def test_accepts_jpg_and_keeps_the_extension(tmp_path):
    root = tmp_path / "jpg_mirror"
    root.mkdir()
    for idx in (0, 600):
        _write_png(root / f"{idx:05d}.jpg", IMG_W, IMG_H)
    (root / "gt.txt").write_text("00000.ppm;10;10;30;30;11\n")

    out = tmp_path / "ds"
    prepare(root, out, "4class")
    assert (out / "_images" / "train" / "00000.jpg").exists()
    assert (out / "gtsdb-4class" / "images" / "train" / "00000.jpg").exists()
    # no annotation for 00600 -> background negative, still needs its .txt
    assert (out / "gtsdb-4class" / "labels" / "val" / "00600.txt").read_text().strip() == ""


def test_png_mirror_survives_ultralytics(tmp_path):
    pytest.importorskip("ultralytics")
    from ultralytics.data.dataset import YOLODataset
    from ultralytics.data.utils import check_det_dataset

    root = tmp_path / "png_mirror"
    root.mkdir()
    lines = []
    for idx in (0, 1, 600, 601):
        _write_png(root / f"{idx:05d}.png", IMG_W, IMG_H)
        lines.append(f"{idx:05d}.ppm;10;10;30;30;1")
    (root / "gt.txt").write_text("\n".join(lines) + "\n")

    summary = prepare(root, tmp_path / "ds", "4class")
    data = check_det_dataset(summary["data_yaml"])
    found = {
        split: sum(len(l["bboxes"]) for l in
                   YOLODataset(img_path=str(data[split]), imgsz=640,
                               data=data, augment=False).labels)
        for split in ("train", "val")
    }
    assert found == {"train": 2, "val": 2}


def test_prefers_the_gt_txt_beside_the_images(tmp_path):
    """A stray gt.txt at the dataset root must not win over the real one.

    Mirrors often keep a top-level gt.txt (or readme) while the images sit in a
    subdirectory with their own gt.txt. Picking the shallowest match finds a
    directory containing no images at all.
    """
    root = tmp_path / "mirror"
    root.mkdir()
    (root / "gt.txt").write_text("00000.ppm;10;10;30;30;1\n")     # stray, no images here
    (root / "ReadMe.txt").write_text("notes\n")

    real = root / "FullIJCNN2013"
    real.mkdir()
    lines = []
    for idx in (0, 1, 600):
        _write_ppm(real / f"{idx:05d}.ppm", IMG_W, IMG_H)
        lines.append(f"{idx:05d}.ppm;10;10;30;30;1")
    (real / "gt.txt").write_text("\n".join(lines) + "\n")

    summary = prepare(root, tmp_path / "ds", "4class")
    assert summary["sources"] == [str(real)]
    assert summary["splits"]["train"]["images"] == 2
    assert summary["splits"]["val"]["images"] == 1


def test_no_images_anywhere_names_the_dirs_that_do_have_them(tmp_path):
    """If no gt.txt dir has images, say where the images actually are."""
    root = tmp_path / "mirror"
    root.mkdir()
    (root / "gt.txt").write_text("00000.ppm;10;10;30;30;1\n")
    pics = root / "Images" / "Train"
    pics.mkdir(parents=True)
    for idx in range(4):
        _write_ppm(pics / f"{idx:05d}.ppm", IMG_W, IMG_H)

    with pytest.raises(FileNotFoundError) as excinfo:
        prepare(root, tmp_path / "ds", "4class")
    message = str(excinfo.value)
    assert "Images/Train" in message.replace("\\", "/"), message
    assert "4 images" in message


def test_image_dir_hint_never_escapes_the_dataset(tmp_path):
    """The 'images are elsewhere' hint must scan --gtsdb-root, nothing above it.

    A first cut walked up to the parent directory, so it happily listed
    unrelated sibling folders on the machine.
    """
    sibling = tmp_path / "unrelated_project"
    (sibling / "photos").mkdir(parents=True)
    for idx in range(3):
        _write_ppm(sibling / "photos" / f"{idx:05d}.ppm", IMG_W, IMG_H)

    root = tmp_path / "mirror"
    root.mkdir()
    (root / "gt.txt").write_text("00000.ppm;10;10;30;30;1\n")
    inside = root / "Images"
    inside.mkdir()
    _write_ppm(inside / "00000.ppm", IMG_W, IMG_H)

    with pytest.raises(FileNotFoundError) as excinfo:
        prepare(root, tmp_path / "ds", "4class")
    message = str(excinfo.value)
    assert "unrelated_project" not in message, message
    assert "Images" in message


def _train_only_root(tmp_path, count=20):
    """The official competition release: only the train set is annotated.

    GTSDB's test ground truth was withheld for the competition, so a faithful
    mirror has 600 labelled train images and 300 unlabelled test images. The
    600-index split rule then puts everything in train.
    """
    root = tmp_path / "official"
    root.mkdir()
    lines = []
    for idx in range(count):
        _write_ppm(root / f"{idx:05d}.ppm", IMG_W, IMG_H)
        lines.append(f"{idx:05d}.ppm;10;10;30;30;1")
    (root / "gt.txt").write_text("\n".join(lines) + "\n")
    return root


def test_split_at_carves_a_val_split_from_labelled_images(tmp_path):
    root = _train_only_root(tmp_path, count=20)
    summary = prepare(root, tmp_path / "ds", "4class", split_at=16)
    assert summary["splits"]["train"]["images"] == 16
    assert summary["splits"]["val"]["images"] == 4
    assert summary["split_at"] == 16


def test_split_at_is_contiguous_not_random(tmp_path):
    """Consecutive GTSDB frames are near-duplicates, so val must be a tail block."""
    root = _train_only_root(tmp_path, count=20)
    out = tmp_path / "ds"
    prepare(root, out, "4class", split_at=16)
    train = {int(p.stem) for p in (out / "_images" / "train").glob("*.png")}
    val = {int(p.stem) for p in (out / "_images" / "val").glob("*.png")}
    assert train == set(range(16))
    assert val == set(range(16, 20))


def test_default_split_at_is_the_official_600(tmp_path):
    root = _train_only_root(tmp_path, count=20)
    with pytest.raises(ValueError, match="empty val split"):
        prepare(root, tmp_path / "ds", "4class")


def test_empty_split_message_suggests_split_at(tmp_path):
    root = _train_only_root(tmp_path, count=20)
    with pytest.raises(ValueError) as excinfo:
        prepare(root, tmp_path / "ds", "4class")
    assert "--split-at" in str(excinfo.value)


def test_split_at_survives_ultralytics(tmp_path):
    pytest.importorskip("ultralytics")
    from ultralytics.data.dataset import YOLODataset
    from ultralytics.data.utils import check_det_dataset

    root = _train_only_root(tmp_path, count=20)
    summary = prepare(root, tmp_path / "ds", "4class", split_at=16)
    data = check_det_dataset(summary["data_yaml"])
    found = {
        split: sum(len(l["bboxes"]) for l in
                   YOLODataset(img_path=str(data[split]), imgsz=640,
                               data=data, augment=False).labels)
        for split in ("train", "val")
    }
    assert found == {"train": 16, "val": 4}


def test_rerun_with_a_different_split_does_not_leak_across_splits(tmp_path):
    """Changing --split-at must not leave an image in BOTH splits.

    images/ was only ever added to, never pruned, so images that moved from
    train to val stayed linked under train as well — silent train/val
    contamination, and the mAP it produces is meaningless.
    """
    root = _train_only_root(tmp_path, count=20)
    out = tmp_path / "ds"

    prepare(root, out, "4class", split_at=16)
    prepare(root, out, "4class", split_at=12)

    train = {p.stem for p in (out / "gtsdb-4class" / "images" / "train").iterdir()}
    val = {p.stem for p in (out / "gtsdb-4class" / "images" / "val").iterdir()}
    assert not (train & val), f"images in both splits: {sorted(train & val)}"
    assert len(train) == 12 and len(val) == 8

    # labels must agree with images, or ultralytics silently reads background
    train_labels = {p.stem for p in (out / "gtsdb-4class" / "labels" / "train").iterdir()}
    assert train_labels == train
