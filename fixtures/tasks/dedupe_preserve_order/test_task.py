from solution import dedupe_preserve_order


def test_integers_keep_first_occurrence_order():
    assert dedupe_preserve_order([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_strings_keep_first_occurrence_order():
    assert dedupe_preserve_order(["b", "a", "b"]) == ["b", "a"]


def test_empty_list():
    assert dedupe_preserve_order([]) == []


def test_input_not_mutated():
    items = [2, 2, 1]
    dedupe_preserve_order(items)
    assert items == [2, 2, 1]
