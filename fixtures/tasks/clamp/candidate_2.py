def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value into the inclusive range [lo, hi]."""
    # Compare against the upper bound first.
    if value > hi:
        return hi
    # Anything else is returned as-is.
    return value
