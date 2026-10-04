def median(values: list) -> float:
    """Return the median of values."""
    # Sort a copy so the caller's list is untouched.
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
