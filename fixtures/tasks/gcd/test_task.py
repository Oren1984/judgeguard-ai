from solution import gcd


def test_common_factor():
    assert gcd(12, 18) == 6


def test_coprime():
    assert gcd(7, 9) == 1


def test_equal_values():
    assert gcd(5, 5) == 5


def test_zero_argument():
    assert gcd(0, 5) == 5
    assert gcd(5, 0) == 5


def test_both_zero():
    assert gcd(0, 0) == 0
