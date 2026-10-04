def running_total(values):
    for i in range(1, len(values)):
        values[i] += values[i - 1]
    return values
