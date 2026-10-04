def running_total(values):
    totals = []
    current = 0
    for value in values:
        current += value
        totals.append(current)
    return totals
