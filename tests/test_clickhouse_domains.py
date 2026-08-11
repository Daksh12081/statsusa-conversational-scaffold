import unittest
from unittest.mock import patch

from nodes.execute_tasks import execute_tasks
from nodes.graph_spec import build_graph_spec
from services.clickhouse_service import ClickHouseQueryError
from services.data_service import data_service


def death_row(year_values: dict) -> dict:
    """Build a mocked ClickHouse row for deaths_and_death_rate: {y2020: '812.40', ...}."""
    return {f"y{year}": value for year, value in year_values.items()}


class DeathQueryTests(unittest.TestCase):
    """'Show the crude death rate in California in 2020' and similar."""

    @patch("services.data_service.clickhouse_service")
    def test_crude_death_rate_california_2020(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "812.40"}]

        result = data_service.execute(
            domain="death",
            state="California",
            year=2020,
            query="Show the crude death rate in California in 2020",
        )

        sql, params = mock_clickhouse.query.call_args[0]
        self.assertIn("y2020", sql)
        self.assertEqual(params["state"], "California")
        self.assertEqual(params["category"], "Crude Rate")

        self.assertEqual(
            result,
            {
                "found": True,
                "domain": "death",
                "state": "California",
                "year": 2020,
                "metric": "Crude Rate",
                "category": "Crude Rate",
                "value": 812.40,
            },
        )

    @patch("services.data_service.clickhouse_service")
    def test_deaths_texas_2020_resolves_deaths_category(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "219828"}]

        result = data_service.execute(
            domain="death",
            state="Texas",
            year=2020,
            query="Show deaths in Texas in 2020",
        )

        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "Deaths")
        self.assertEqual(result["value"], 219828)

    @patch("services.data_service.clickhouse_service")
    def test_age_adjusted_rate_florida_2020(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "705.3"}]

        result = data_service.execute(
            domain="death",
            state="Florida",
            year=2020,
            query="Show the age adjusted death rate in Florida in 2020",
        )

        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "Age Adjusted Rate")
        self.assertEqual(result["metric"], "Age Adjusted Rate")

    @patch("services.data_service.clickhouse_service")
    def test_rank_top_5_states_by_crude_rate_2020(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [
            {"state": name, "value": str(value)}
            for name, value in [
                ("Mississippi", 1200.1),
                ("West Virginia", 1150.4),
                ("Alabama", 1100.2),
                ("Kentucky", 1080.9),
                ("Arkansas", 1050.3),
            ]
        ]

        results = data_service.rank(
            domain="death",
            year=2020,
            top_n=5,
            query="Show the top 5 states by crude death rate in 2020",
        )

        sql, params = mock_clickhouse.query.call_args[0]
        self.assertIn("y2020", sql)
        self.assertEqual(params["top_n"], 5)
        self.assertEqual(params["category"], "Crude Rate")
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["state"], "Mississippi")

    @patch("services.data_service.clickhouse_service")
    def test_invalid_year_rejected_without_querying(self, mock_clickhouse):
        result = data_service.execute(domain="death", state="Texas", year=1800)

        mock_clickhouse.query.assert_not_called()
        self.assertFalse(result["found"])

    @patch("services.data_service.clickhouse_service")
    def test_no_year_resolves_latest_available_year_dynamically(self, mock_clickhouse):
        # y2024 has no data yet, y2023 does -- proves the code picks whatever
        # the data says is latest, rather than a hardcoded constant.
        row = death_row({2024: None, 2023: "730.7", 2022: "812.4"})
        mock_clickhouse.query.return_value = [row]

        result = data_service.execute(
            domain="death",
            state="California",
            year=None,
            query="Show the crude death rate in California",
        )

        self.assertEqual(result["year"], 2023)
        self.assertEqual(result["value"], 730.7)

    @patch("services.data_service.clickhouse_service")
    def test_clickhouse_error_reported_distinctly_from_no_data(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = ClickHouseQueryError("connection refused")

        result = data_service.execute(domain="death", state="Texas", year=2020)

        self.assertFalse(result["found"])
        self.assertIn("unavailable", result["message"])


class HousingQueryTests(unittest.TestCase):
    """Housing now queries ClickHouse's housing_prices table (migration complete)."""

    @patch("services.data_service.clickhouse_service")
    def test_median_home_price_texas_2020(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "290000.5"}]

        result = data_service.execute(
            domain="housing",
            state="Texas",
            year=2020,
            query="Show the median home price in Texas in 2020",
        )

        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "median_listing_price")
        self.assertEqual(params["year"], 2020)
        self.assertEqual(result["value"], 290000.5)
        self.assertTrue(result["found"])

    @patch("services.data_service.clickhouse_service")
    def test_median_home_price_california_2020(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "650748.0"}]

        result = data_service.execute(
            domain="housing",
            state="California",
            year=2020,
            query="Show the median home price in California in 2020",
        )

        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["state"], "California")
        self.assertEqual(params["category"], "median_listing_price")
        self.assertEqual(result["value"], 650748.0)

    @patch("services.data_service.clickhouse_service")
    def test_home_value_and_average_home_price_phrasing_resolve_categories(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "500000"}]

        data_service.execute(domain="housing", state="Texas", year=2020, query="What is the home value in Texas in 2020")
        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "median_listing_price")

        data_service.execute(domain="housing", state="Texas", year=2020, query="What is the average home price in Texas in 2020")
        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "average_listing_price")

    @patch("services.data_service.clickhouse_service")
    def test_normalized_output_includes_backward_compat_field(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "650748.0"}]

        result = data_service.execute(
            domain="housing",
            state="California",
            year=2020,
            query="Show the median home price in California in 2020",
        )

        self.assertEqual(
            result,
            {
                "found": True,
                "domain": "housing",
                "state": "California",
                "year": 2020,
                "metric": "median_listing_price",
                "category": "median_listing_price",
                "value": 650748.0,
                "median_home_price": 650748.0,
            },
        )

    @patch("services.data_service.clickhouse_service")
    def test_rank_top_10_states_by_home_price(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [
            {"state": name, "value": str(value)}
            for name, value in [
                ("Hawaii", 950000.0),
                ("California", 800000.0),
                ("Massachusetts", 700000.0),
                ("Washington", 650000.0),
                ("Colorado", 600000.0),
                ("New York", 590000.0),
                ("New Jersey", 550000.0),
                ("Oregon", 520000.0),
                ("Utah", 500000.0),
                ("Nevada", 480000.0),
            ]
        ]

        results = data_service.rank(
            domain="housing",
            year=2022,
            top_n=10,
            query="Top 10 states by median home price",
        )

        sql, params = mock_clickhouse.query.call_args[0]
        self.assertIn("state != 'US'", sql)
        self.assertEqual(params["top_n"], 10)
        self.assertEqual(params["category"], "median_listing_price")
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0]["state"], "Hawaii")
        self.assertTrue(all("median_home_price" in item for item in results))

    @patch("services.data_service.clickhouse_service")
    def test_no_year_resolves_latest_available_year_dynamically(self, mock_clickhouse):
        # first call finds the latest year with real data, second fetches it.
        mock_clickhouse.query.side_effect = [
            [{"latest_year": 2021}],
            [{"value": "410000"}],
        ]

        result = data_service.execute(
            domain="housing", state="Texas", year=None, query="median home price in Texas"
        )

        self.assertEqual(result["year"], 2021)
        self.assertEqual(result["value"], 410000.0)


class ExecuteTasksCompareTests(unittest.TestCase):
    """'Compare the death rate in Texas and California in 2020'."""

    @patch("nodes.execute_tasks.data_service")
    def test_compare_task_queries_both_states(self, mock_data_service):
        mock_data_service.execute.side_effect = [
            {"found": True, "domain": "death", "state": "Texas", "year": 2020, "metric": "Crude Rate", "value": 900.0},
            {"found": True, "domain": "death", "state": "California", "year": 2020, "metric": "Crude Rate", "value": 812.4},
        ]

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "death",
                    "query": "Compare the death rate in Texas and California in 2020",
                    "depends_on": [],
                }
            ],
            "current_intent": {"metrics": ["death rate"]},
            "response_mode": "compare",
        }

        output = execute_tasks(state)
        result = output["task_results"][0]["result"]

        self.assertEqual(mock_data_service.execute.call_count, 2)
        called_states = {call.kwargs["state"] for call in mock_data_service.execute.call_args_list}
        self.assertEqual(called_states, {"Texas", "California"})
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(result["found"])

    @patch("nodes.execute_tasks.data_service")
    def test_compare_housing_task_queries_both_states(self, mock_data_service):
        mock_data_service.execute.side_effect = [
            {"found": True, "domain": "housing", "state": "Texas", "year": 2020, "metric": "median_listing_price", "value": 345000.0, "median_home_price": 345000.0},
            {"found": True, "domain": "housing", "state": "California", "year": 2020, "metric": "median_listing_price", "value": 650748.0, "median_home_price": 650748.0},
        ]

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "housing",
                    "query": "Compare the median home price in Texas and California in 2020",
                    "depends_on": [],
                }
            ],
            "current_intent": {"metrics": ["median home price"]},
            "response_mode": "compare",
        }

        output = execute_tasks(state)
        result = output["task_results"][0]["result"]

        self.assertEqual(mock_data_service.execute.call_count, 2)
        called_states = {call.kwargs["state"] for call in mock_data_service.execute.call_args_list}
        self.assertEqual(called_states, {"Texas", "California"})
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(result["found"])


class GraphSpecTests(unittest.TestCase):
    """graph_spec should use the normalized value/metric shape for death and housing."""

    def test_death_single_result_uses_normalized_value(self):
        state = {
            "graph_needed": True,
            "graph_type": "bar",
            "graph_title": "Crude Rate (2020)",
            "task_results": [
                {
                    "result": {
                        "found": True,
                        "state": "California",
                        "year": 2020,
                        "metric": "Crude Rate",
                        "value": 812.4,
                    }
                }
            ],
        }

        output = build_graph_spec(state)

        self.assertEqual(
            output["graph_spec"]["data"],
            [{"State": "California", "Value": 812.4, "Metric": "Crude Rate"}],
        )

    def test_housing_ranked_items_use_backward_compat_field(self):
        state = {
            "graph_needed": True,
            "graph_type": "horizontal_bar",
            "graph_title": "Median Home Price (2022)",
            "task_results": [
                {
                    "result": {
                        "items": [
                            {"state": "Hawaii", "year": 2022, "metric": "median_listing_price", "value": 950000.0, "median_home_price": 950000.0},
                            {"state": "California", "year": 2022, "metric": "median_listing_price", "value": 800000.0, "median_home_price": 800000.0},
                        ]
                    }
                }
            ],
        }

        output = build_graph_spec(state)

        self.assertEqual(
            output["graph_spec"]["data"],
            [
                {"State": "Hawaii", "Value": 950000.0, "Metric": "Median Home Price"},
                {"State": "California", "Value": 800000.0, "Metric": "Median Home Price"},
            ],
        )

    def test_no_graph_needed_returns_none(self):
        output = build_graph_spec({"graph_needed": False})
        self.assertIsNone(output["graph_spec"])


if __name__ == "__main__":
    unittest.main()
