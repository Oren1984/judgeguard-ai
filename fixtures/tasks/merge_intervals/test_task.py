from solution import merge_intervals


def test_sorted_overlapping():
    assert merge_intervals([(1, 3), (2, 4), (6, 7)]) == [(1, 4), (6, 7)]


def test_touching_intervals_merge():
    assert merge_intervals([(1, 2), (2, 3)]) == [(1, 3)]


def test_unsorted_input():
    assert merge_intervals([(5, 6), (1, 3), (2, 4)]) == [(1, 4), (5, 6)]


def test_empty_input():
    assert merge_intervals([]) == []
