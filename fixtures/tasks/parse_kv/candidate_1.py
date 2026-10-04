SEPARATOR = DEFAULT_SEPARATOR


def parse_kv(text: str) -> dict:
    """Parse 'key=value' pairs separated by the configured separator."""
    result = {}
    for part in text.split(SEPARATOR):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip()] = value.strip()
    return result
