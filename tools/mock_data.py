MOCK_INSURANCE = {
    ("Texas", 2022): {"uninsured_rate": 16.6},
    ("California", 2022): {"uninsured_rate": 7.9},
    ("Florida", 2022): {"uninsured_rate": 12.5},
    ("New York", 2022): {"uninsured_rate": 5.2},
}


# housing and death now query ClickHouse directly (see services/data_service.py).
# insurance stays on mock data until its ClickHouse table is populated.
DATASETS = {
    "insurance": MOCK_INSURANCE,
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
