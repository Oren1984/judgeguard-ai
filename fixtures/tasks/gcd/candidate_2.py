def gcd(a: int, b: int) -> int:
    """Greatest common divisor by repeated subtraction."""
    # Keep subtracting the smaller value from the larger one.
    while a != b:
        if a > b:
            a -= b
        else:
            b -= a
    return a
