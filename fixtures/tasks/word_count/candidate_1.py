from collections import Counter


def word_count(text):
    return dict(Counter(text.lower().split()))
