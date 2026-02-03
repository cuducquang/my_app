def estimate_trip_cost(days: int, people: int, base_cost_per_day: float, group_type: str) -> float:
    group_multiplier = {
        "solo": 1.1,
        "couple": 1.0,
        "family": 0.95,
        "group": 0.9,
    }.get(group_type, 1.0)
    return round(days * people * base_cost_per_day * group_multiplier, 2)

