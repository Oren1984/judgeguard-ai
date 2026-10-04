def is_palindrome(text: str) -> bool:
    """Return True when text is a palindrome, ignoring letter case."""
    # Normalise the case so 'A' and 'a' compare equal.
    lowered = text.lower()
    # Compare the string with its reverse.
    return lowered == lowered[::-1]
