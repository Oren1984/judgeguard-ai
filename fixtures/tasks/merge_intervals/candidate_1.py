def merge_intervals(intervals: list) -> list:
    """Merge overlapping or touching intervals and return them sorted."""
    merged = []
    for start, end in sorted(intervals):
        # Extend the previous interval when this one overlaps or touches it.
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
