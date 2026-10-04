def chunk_list(items: list, size: int) -> list:
    chunks = []
    # Walk over every complete chunk.
    for index in range(len(items) // size):
        start = index * size
        chunks.append(items[start:start + size])
    return chunks
