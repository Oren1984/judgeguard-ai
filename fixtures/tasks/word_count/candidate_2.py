def word_count(text: str) -> dict:
    """Count how often each lowercase word appears in text."""
    counts = {}
    for word in text.lower().split():
        # Start at zero for words we have not seen yet.
        counts[word] = counts.get(word, 0) + 1
    return counts
