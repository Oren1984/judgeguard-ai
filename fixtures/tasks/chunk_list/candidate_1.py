def chunk_list(items, size):
    """Split items into consecutive chunks of at most size elements."""
    return [items[i:i + size] for i in range(0, len(items), size)]
