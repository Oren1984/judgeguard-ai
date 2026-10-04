def safe_divide(a: float, b: float, default=None):
    """Divide a by b, falling back to default when b is zero."""
    try:
        return a / b
    except ZeroDivisionError:
        # Division by zero is the only failure we expect here.
        return default
