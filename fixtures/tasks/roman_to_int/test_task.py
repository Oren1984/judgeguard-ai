from solution import roman_to_int


def test_additive():
    assert roman_to_int("VIII") == 8


def test_subtractive_pairs():
    assert roman_to_int("IV") == 4
    assert roman_to_int("IX") == 9


def test_mixed():
    assert roman_to_int("MCMXCIV") == 1994
