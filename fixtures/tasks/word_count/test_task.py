from solution import word_count


def test_repeated_words():
    assert word_count("a b a") == {"a": 2, "b": 1}


def test_mixed_case_is_folded():
    assert word_count("Tea tea TEA") == {"tea": 3}


def test_irregular_whitespace():
    assert word_count("  x \t y\n x ") == {"x": 2, "y": 1}


def test_empty_text():
    assert word_count("") == {}
