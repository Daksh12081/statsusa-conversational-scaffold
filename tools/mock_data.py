MOCK_INSURANCE = {
    ("Texas", 2022): {"uninsured_rate": 16.6},
    ("California", 2022): {"uninsured_rate": 7.9},
    ("Florida", 2022): {"uninsured_rate": 12.5},
    ("New York", 2022): {"uninsured_rate": 5.2},
}


MOCK_HOUSING = {
    ("Texas", 2022): {"median_home_price": 345000},
    ("California", 2022): {"median_home_price": 786000},
    ("Florida", 2022): {"median_home_price": 410000},
    ("New York", 2022): {"median_home_price": 462000},
}


MOCK_DEATH = {
    ("Texas", 2022): {"death_rate": 8.1},
    ("California", 2022): {"death_rate": 6.4},
    ("Florida", 2022): {"death_rate": 10.2},
    ("New York", 2022): {"death_rate": 7.3},
}


DATASETS = {
    "insurance": MOCK_INSURANCE,
    "housing": MOCK_HOUSING,
    "death": MOCK_DEATH,
}


def lookup(domain: str, state: str, year: int):
    dataset = DATASETS.get(domain, {})
    result = dataset.get((state, year))

    if result is None:
        return {
            "found": False,
            "message": f"No mock data found for {state} ({year}).",
        }

    return {
        "found": True,
        "state": state,
        "year": year,
        "domain": domain,
        **result,
    }