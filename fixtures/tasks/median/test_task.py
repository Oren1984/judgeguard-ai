from solution import median


def test_odd_count_unsorted():
    assert median([3, 1, 2]) == 2


def test_even_count_uses_mean_of_middle_pair():
    assert median([1, 2, 3, 4]) == 2.5


def test_single_element():
    assert median([7]) == 7


def test_input_not_mutated():
    values = [3, 1, 2]
    median(values)
    assert values == [3, 1, 2]
