from solution import is_palindrome


def test_simple_palindrome():
    assert is_palindrome("racecar") is True


def test_mixed_case():
    assert is_palindrome("Level") is True


def test_phrase_with_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama") is True


def test_non_palindrome():
    assert is_palindrome("hello") is False


def test_empty_string():
    assert is_palindrome("") is True
