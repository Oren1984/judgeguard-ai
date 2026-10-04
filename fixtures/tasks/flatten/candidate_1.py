def flatten(nested: list) -> list:
    """Flatten nested lists into a single flat list."""
    flat = []
    for item in nested:
        # Lists are expanded, plain values are kept.
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat
