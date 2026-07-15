
from tools.mock_data import DATASETS, lookup


class DataService:
    """Backend abstraction layer.

    Today this uses mock data.
    Later this class can call SQL, OLAP, Elasticsearch,
    Vector DBs, or external APIs without changing LangGraph.
    """

    def execute(self, domain: str, state: str, year: int) -> dict:
        return lookup(domain, state, year)

    def rank(self, domain: str, year: int, top_n: int) -> list[dict]:
        dataset = DATASETS.get(domain, {})

        metric_name = {
            "insurance": "uninsured_rate",
            "housing": "median_home_price",
            "death": "death_rate",
        }[domain]

        items = []

        for (state_name, data_year), values in dataset.items():
            if data_year != year:
                continue

            items.append(
                {
                    "state": state_name,
                    "year": data_year,
                    metric_name: values[metric_name],
                }
            )

        items.sort(key=lambda item: item[metric_name], reverse=True)
        return items[:top_n]


# Singleton instance used throughout the application.
data_service = DataService()
