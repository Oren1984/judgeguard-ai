def dedupe_preserve_order(items: list) -> list:
    """Return items without duplicates, keeping first occurrences in order."""
    seen = set()
    result = []
    for item in items:
        # Skip anything we have already emitted.
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
