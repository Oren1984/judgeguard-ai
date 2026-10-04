from solution import chunk_list


def test_exact_multiple():
    assert chunk_list([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_remainder_becomes_short_final_chunk():
    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_size_larger_than_list():
    assert chunk_list([1, 2], 5) == [[1, 2]]


def test_empty_list():
    assert chunk_list([], 3) == []
