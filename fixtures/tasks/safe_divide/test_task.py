from solution import safe_divide


def test_ordinary_division():
    assert safe_divide(6, 3) == 2


def test_zero_divisor_returns_none_by_default():
    assert safe_divide(1, 0) is None


def test_zero_divisor_returns_explicit_default():
    assert safe_divide(1, 0, default=-1) == -1
