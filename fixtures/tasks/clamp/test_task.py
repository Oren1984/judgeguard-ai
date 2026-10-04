from solution import clamp


def test_inside_range():
    assert clamp(5, 0, 10) == 5


def test_below_lower_bound():
    assert clamp(-3, 0, 10) == 0


def test_above_upper_bound():
    assert clamp(42, 0, 10) == 10


def test_bounds_are_inclusive():
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10
