def flatten(n):
    o = []
    for x in n:
        o += flatten(x) if isinstance(x, list) else [x]
    return o
