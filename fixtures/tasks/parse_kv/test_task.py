from solution import parse_kv


def test_two_pairs():
    assert parse_kv("a=1;b=2") == {"a": "1", "b": "2"}


def test_whitespace_is_stripped():
    assert parse_kv(" a = 1 ; b=2 ") == {"a": "1", "b": "2"}


def test_segments_without_equals_are_ignored():
    assert parse_kv("a=1;;junk;b=2") == {"a": "1", "b": "2"}


def test_empty_input():
    assert parse_kv("") == {}
