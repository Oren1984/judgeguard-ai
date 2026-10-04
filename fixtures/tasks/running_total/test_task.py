from solution import running_total


def test_positive_values():
    assert running_total([1, 2, 3]) == [1, 3, 6]


def test_negative_values():
    assert running_total([5, -2, -4]) == [5, 3, -1]


def test_empty_list():
    assert running_total([]) == []


def test_input_not_mutated():
    values = [1, 2, 3]
    running_total(values)
    assert values == [1, 2, 3]
