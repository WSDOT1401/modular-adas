"""Unit tests for the GTSDB label-set mappings — pure data, no dataset needed.

The 4-class grouping is 43 hand-typed ids across four buckets; the partition
test below is what catches a duplicated or dropped id.
"""
import pytest

from classes import GTSDB_NUM_CLASSES, LABEL_SETS, SUPER_CLASS_IDS, label_set


def test_super_classes_partition_all_43_ids():
    ids = [i for bucket in SUPER_CLASS_IDS.values() for i in bucket]
    assert len(ids) == GTSDB_NUM_CLASSES        # no id typed twice, none dropped
    assert sorted(ids) == list(range(GTSDB_NUM_CLASSES))


def test_super_class_buckets_are_disjoint():
    seen: set[int] = set()
    for name, bucket in SUPER_CLASS_IDS.items():
        assert not seen & set(bucket), f"{name} overlaps an earlier bucket"
        assert len(set(bucket)) == len(bucket), f"{name} lists an id twice"
        seen |= set(bucket)


def test_4class_names_and_order():
    names, mapping = label_set("4class")
    assert names == ["prohibitory", "danger", "mandatory", "other"]
    assert len(mapping) == GTSDB_NUM_CLASSES
    # one representative per bucket, in declared order
    assert mapping[1] == 0      # 30 km/h speed limit -> prohibitory
    assert mapping[11] == 1     # priority at next intersection -> danger
    assert mapping[33] == 2     # turn right ahead -> mandatory
    assert mapping[6] == 3      # end of speed limit -> other


def test_1class_collapses_everything():
    names, mapping = label_set("1class")
    assert names == ["sign"]
    assert len(mapping) == GTSDB_NUM_CLASSES
    assert set(mapping.values()) == {0}


def test_every_label_set_maps_every_gtsdb_id():
    for name in LABEL_SETS:
        names, mapping = label_set(name)
        assert sorted(mapping) == list(range(GTSDB_NUM_CLASSES)), name
        assert set(mapping.values()) == set(range(len(names))), name


def test_unknown_label_set_raises():
    with pytest.raises(KeyError):
        label_set("43class")
