import unittest
from unittest.mock import patch

from nodes.execute_tasks import execute_tasks, extract_states
from nodes.graph_spec import build_graph_spec
from services.clickhouse_service import ClickHouseQueryError
from services.data_service import (
    DEATH_TABLE,
    clear_metadata_cache,
    data_service,
    get_available_states,
    get_available_years,
    get_latest_available_year,
    get_year_range,
    validate_grand_total_filters,
)


def death_row(year_values: dict) -> dict:
    """Build a mocked ClickHouse row for deaths_and_death_rate: {y2020: '812.40', ...}."""
    return {f"y{year}": value for year, value in year_values.items()}


class DeathQueryTests(unittest.TestCase):
    """'Show the crude death rate in California in 2020' and similar."""

    def setUp(self):
        clear_metadata_cache()

        year_range_patcher = patch(
            "services.data_service.get_year_range", return_value=(1999, 2024)
        )
        self.addCleanup(year_range_patcher.stop)
        year_range_patcher.start()

        columns_patcher = patch(
            "services.data_service._discover_year_columns",
            return_value=["y2022", "y2023", "y2024"],
        )
        self.addCleanup(columns_patcher.stop)
        columns_patcher.start()

    @patch("services.data_service.clickhouse_service")
    def test_comma_formatted_value_is_parsed(self, mock_clickhouse):
        # Regression test: Ohio's real y2020 crude rate is stored as "1,228.90"
        # (thousands separator). A naive float() call rejects this and was
        # silently reporting found=False for real data -- caught via live
        # verification once state coverage expanded beyond the old 4-state list.
        mock_clickhouse.query.return_value = [{"value": "1,228.90"}]

        result = data_service.execute(
            domain="death",
            state="Ohio",
            year=2020,
            query="Show the crude death rate in Ohio in 2020",
        )

        self.assertTrue(result["found"])
        self.assertEqual(result["value"], 1228.90)

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


class InsuranceQueryTests(unittest.TestCase):
    """Insurance now queries ClickHouse's health_insurance table (migration complete)."""

    def setUp(self):
        clear_metadata_cache()

        year_range_patcher = patch(
            "services.data_service.get_year_range", return_value=(2015, 2024)
        )
        self.addCleanup(year_range_patcher.stop)
        year_range_patcher.start()

        columns_patcher = patch(
            "services.data_service._discover_year_columns",
            return_value=["y2022", "y2023", "y2024"],
        )
        self.addCleanup(columns_patcher.stop)
        columns_patcher.start()

    @patch("services.data_service.clickhouse_service")
    def test_uninsured_rate_texas_2022(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "17.6"}]

        result = data_service.execute(
            domain="insurance",
            state="Texas",
            year=2022,
            query="What's the uninsured rate in Texas in 2022?",
        )

        sql, params = mock_clickhouse.query.call_args[0]
        self.assertIn("y2022", sql)
        self.assertEqual(params["state"], "Texas")
        self.assertEqual(params["category"], "Percent Uninsured")
        self.assertEqual(params["parent_category"], "Uninsured Population (Percent) by Age")

        self.assertEqual(
            result,
            {
                "found": True,
                "domain": "insurance",
                "state": "Texas",
                "year": 2022,
                "metric": "Percent Uninsured",
                "category": "Percent Uninsured",
                "value": 17.6,
                "units": "percent",
                "uninsured_rate": 17.6,
            },
        )

    @patch("services.data_service.clickhouse_service")
    def test_insured_population_retrieval(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "23708399"}]

        result = data_service.execute(
            domain="insurance",
            state="Texas",
            year=2022,
            query="Show insured population in Texas in 2022",
        )

        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "Insured")
        self.assertEqual(result["value"], 23708399)
        self.assertEqual(result["units"], "number")
        self.assertNotIn("uninsured_rate", result)

    @patch("services.data_service.clickhouse_service")
    def test_percent_insured_retrieval(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"value": "92.9"}]

        result = data_service.execute(
            domain="insurance",
            state="California",
            year=2022,
            query="What percent of California is insured in 2022?",
        )

        _, params = mock_clickhouse.query.call_args[0]
        self.assertEqual(params["category"], "Percent Insured")
        self.assertEqual(result["metric"], "Percent Insured")
        self.assertEqual(result["value"], 92.9)

    @patch("services.data_service.clickhouse_service")
    def test_rank_top_5_states_by_uninsured_rate_2022(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [
            {"state": name, "value": str(value)}
            for name, value in [
                ("Texas", 17.6),
                ("Oklahoma", 13.9),
                ("Georgia", 12.9),
                ("Florida", 12.3),
                ("Mississippi", 11.8),
            ]
        ]

        results = data_service.rank(
            domain="insurance",
            year=2022,
            top_n=5,
            query="Top 5 states by uninsured rate in 2022",
        )

        sql, params = mock_clickhouse.query.call_args[0]
        self.assertIn("y2022", sql)
        self.assertIn("state != 'US'", sql)
        self.assertEqual(params["top_n"], 5)
        self.assertEqual(params["category"], "Percent Uninsured")
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["state"], "Texas")
        self.assertTrue(all("uninsured_rate" in item for item in results))

    @patch("services.data_service.clickhouse_service")
    def test_no_year_resolves_latest_available_year_dynamically(self, mock_clickhouse):
        row = death_row({2024: "17.1", 2023: "17.4", 2022: "17.6"})
        mock_clickhouse.query.return_value = [row]

        result = data_service.execute(
            domain="insurance", state="Texas", year=None, query="uninsured rate in Texas"
        )

        self.assertEqual(result["year"], 2024)
        self.assertEqual(result["value"], 17.1)

    @patch("services.data_service.clickhouse_service")
    def test_clickhouse_error_reported_distinctly_from_no_data(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = ClickHouseQueryError("connection refused")

        result = data_service.execute(domain="insurance", state="Texas", year=2022)

        self.assertFalse(result["found"])
        self.assertIn("unavailable", result["message"])

    @unittest.skip(
        "Legislative/congressional-district geography is confirmed present in "
        "health_insurance (fips_val_type='CLD'/'SLD') but there is no natural-language "
        "extraction for it anywhere in the current planner (execute_tasks.py only "
        "extracts state names); wiring that up was scoped out of this migration per "
        "the approved Phase 1 report and left as documented future work."
    )
    def test_legislative_district_geography_query(self):
        pass


class ExecuteTasksCompareTests(unittest.TestCase):
    """'Compare the death rate in Texas and California in 2020'."""

    def setUp(self):
        clear_metadata_cache()

        states_patcher = patch(
            "nodes.execute_tasks.get_available_states",
            return_value=["California", "Florida", "New York", "Texas"],
        )
        self.addCleanup(states_patcher.stop)
        states_patcher.start()

        years_patcher = patch("nodes.execute_tasks.get_available_years", return_value=[])
        self.addCleanup(years_patcher.stop)
        years_patcher.start()

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

    @patch("nodes.execute_tasks.data_service")
    def test_compare_insurance_task_queries_both_states(self, mock_data_service):
        mock_data_service.execute.side_effect = [
            {"found": True, "domain": "insurance", "state": "Texas", "year": 2022, "metric": "Percent Uninsured", "value": 17.6, "units": "percent", "uninsured_rate": 17.6},
            {"found": True, "domain": "insurance", "state": "California", "year": 2022, "metric": "Percent Uninsured", "value": 6.2, "units": "percent", "uninsured_rate": 6.2},
        ]

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "insurance",
                    "query": "Compare the uninsured rate in Texas and California in 2022",
                    "depends_on": [],
                }
            ],
            "current_intent": {"metrics": ["uninsured rate"]},
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
    def test_multi_domain_query_insurance_and_housing(self, mock_data_service):
        """A multi-task plan spanning insurance + housing (e.g. response_mode='separate')."""
        mock_data_service.execute.side_effect = [
            {"found": True, "domain": "insurance", "state": "Texas", "year": 2022, "metric": "Percent Uninsured", "value": 17.6, "units": "percent", "uninsured_rate": 17.6},
            {"found": True, "domain": "housing", "state": "Texas", "year": 2022, "metric": "median_listing_price", "value": 345000.0, "median_home_price": 345000.0},
        ]

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "insurance",
                    "query": "Show the uninsured rate in Texas in 2022",
                    "depends_on": [],
                },
                {
                    "task_id": "task_2",
                    "domain": "housing",
                    "query": "Show the median home price in Texas in 2022",
                    "depends_on": [],
                },
            ],
            "current_intent": {"metrics": ["uninsured rate", "median home price"]},
            "response_mode": "separate",
        }

        output = execute_tasks(state)
        task_results = output["task_results"]

        self.assertEqual(len(task_results), 2)
        self.assertEqual(task_results[0]["result"]["domain"], "insurance")
        self.assertEqual(task_results[1]["result"]["domain"], "housing")
        called_domains = [call.kwargs["domain"] for call in mock_data_service.execute.call_args_list]
        self.assertEqual(called_domains, ["insurance", "housing"])


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

    def test_insurance_ranked_items_use_backward_compat_field(self):
        state = {
            "graph_needed": True,
            "graph_type": "horizontal_bar",
            "graph_title": "Uninsured Rate (2022)",
            "task_results": [
                {
                    "result": {
                        "items": [
                            {"state": "Texas", "year": 2022, "metric": "Percent Uninsured", "value": 17.6, "uninsured_rate": 17.6},
                            {"state": "Oklahoma", "year": 2022, "metric": "Percent Uninsured", "value": 13.9, "uninsured_rate": 13.9},
                        ]
                    }
                }
            ],
        }

        output = build_graph_spec(state)

        self.assertEqual(
            output["graph_spec"]["data"],
            [
                {"State": "Texas", "Value": 17.6, "Metric": "Uninsured Rate"},
                {"State": "Oklahoma", "Value": 13.9, "Metric": "Uninsured Rate"},
            ],
        )

    def test_insurance_non_uninsured_metric_uses_generic_value(self):
        state = {
            "graph_needed": True,
            "graph_type": "bar",
            "graph_title": "Insured Population (2022)",
            "task_results": [
                {
                    "result": {
                        "found": True,
                        "state": "Texas",
                        "metric": "Insured",
                        "value": 23708399.0,
                    }
                }
            ],
        }

        output = build_graph_spec(state)

        self.assertEqual(
            output["graph_spec"]["data"],
            [{"State": "Texas", "Value": 23708399.0, "Metric": "Insured"}],
        )


class YearMetadataTests(unittest.TestCase):
    """get_available_years / get_year_range / get_latest_available_year."""

    def setUp(self):
        clear_metadata_cache()

    @patch("services.data_service.clickhouse_service")
    def test_death_years_exclude_unpopulated_years(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = [
            [{"name": "y2022"}, {"name": "y2023"}, {"name": "y2024"}],
            [{"y2022": 53, "y2023": 53, "y2024": 0}],
        ]

        years = get_available_years("death")

        self.assertEqual(years, [2022, 2023])

        columns_sql, columns_params = mock_clickhouse.query.call_args_list[0][0]
        self.assertIn("system.columns", columns_sql)
        self.assertEqual(columns_params["table"], DEATH_TABLE)

        counts_sql, _ = mock_clickhouse.query.call_args_list[1][0]
        self.assertIn("countIf", counts_sql)
        self.assertNotIn("state = 'US'", counts_sql)

    @patch("services.data_service.clickhouse_service")
    def test_death_year_range_1999_to_2024(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = [
            [{"name": "y1999"}, {"name": "y2000"}, {"name": "y2024"}],
            [{"y1999": 10, "y2000": 40, "y2024": 53}],
        ]

        self.assertEqual(get_year_range("death"), (1999, 2024))

    @patch("services.data_service.clickhouse_service")
    def test_insurance_latest_available_year(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = [
            [{"name": "y2023"}, {"name": "y2024"}],
            [{"y2023": 52, "y2024": 0}],
        ]

        self.assertEqual(get_latest_available_year("insurance"), 2023)

    @patch("services.data_service.clickhouse_service")
    def test_housing_years_exclude_na_placeholder_years(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [
            {"year": 2016}, {"year": 2020}, {"year": 2025}
        ]

        years = get_available_years("housing")

        self.assertEqual(years, [2016, 2020, 2025])
        sql, _ = mock_clickhouse.query.call_args[0]
        self.assertIn("avg != 'NA'", sql)
        self.assertIn("DISTINCT year", sql)
        self.assertEqual(get_year_range("housing"), (2016, 2025))

    @patch("services.data_service.clickhouse_service")
    def test_year_range_none_when_no_years_available(self, mock_clickhouse):
        mock_clickhouse.query.return_value = []

        self.assertIsNone(get_year_range("housing"))
        self.assertIsNone(get_latest_available_year("housing"))


class StateResolverTests(unittest.TestCase):
    """Dynamic geography resolution, replacing the old 4-state regex."""

    def setUp(self):
        clear_metadata_cache()

    @patch("services.data_service.clickhouse_service")
    def test_get_available_states_excludes_national_aggregate(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [
            {"area_name": "Ohio"}, {"area_name": "Massachusetts"}, {"area_name": "Texas"},
        ]

        states = get_available_states("death")

        sql, _ = mock_clickhouse.query.call_args[0]
        self.assertIn("state != 'US'", sql)
        self.assertEqual(states, ["Ohio", "Massachusetts", "Texas"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_extract_states_finds_state_outside_old_four_state_list(self, mock_get_states):
        mock_get_states.return_value = ["Ohio", "Massachusetts", "Texas", "California"]

        result = extract_states("Show the uninsured rate in Ohio in 2022", "insurance")

        self.assertEqual(result, ["Ohio"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_extract_states_multi_state_outside_old_list(self, mock_get_states):
        mock_get_states.return_value = ["Ohio", "Massachusetts", "Texas", "California"]

        result = extract_states(
            "Compare the uninsured rate in Ohio and Massachusetts", "insurance"
        )

        self.assertEqual(result, ["Ohio", "Massachusetts"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_extract_states_prefers_longer_name_over_substring(self, mock_get_states):
        mock_get_states.return_value = ["Virginia", "West Virginia"]

        result = extract_states("median home price in West Virginia", "housing")

        self.assertEqual(result, ["West Virginia"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_extract_states_case_insensitive(self, mock_get_states):
        mock_get_states.return_value = ["Ohio"]

        self.assertEqual(extract_states("uninsured rate in ohio", "insurance"), ["Ohio"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_extract_states_no_match_returns_empty(self, mock_get_states):
        mock_get_states.return_value = ["Ohio", "Texas"]

        self.assertEqual(extract_states("uninsured rate somewhere", "insurance"), [])

    @patch("nodes.execute_tasks.get_available_states")
    def test_national_aggregate_not_confused_with_a_specific_state(self, mock_get_states):
        # "United States" must resolve to the distinct "US" national-aggregate
        # token, never to one of the actual per-state names in the dynamic list.
        mock_get_states.return_value = ["Texas", "California"]

        result = extract_states("What about the United States overall in 2020", "death")

        self.assertEqual(result, ["US"])


class StateAliasTests(unittest.TestCase):
    """Alias normalization layered on top of the dynamic state resolver."""

    ALL_STATES = [
        "California",
        "Texas",
        "New York",
        "Massachusetts",
        "Virginia",
        "West Virginia",
        "District of Columbia",
        "Florida",
        "Pennsylvania",
        "Illinois",
        "Washington",
        "North Carolina",
        "South Carolina",
        "North Dakota",
        "South Dakota",
    ]

    @patch("nodes.execute_tasks.get_available_states")
    def test_ca_resolves_to_california(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES
        self.assertEqual(extract_states("uninsured rate in CA", "insurance"), ["California"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_tx_resolves_to_texas(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES
        self.assertEqual(extract_states("median home price in TX", "housing"), ["Texas"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_ny_and_ny_state_resolve_to_new_york(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES
        self.assertEqual(extract_states("crude death rate in NY", "death"), ["New York"])
        self.assertEqual(extract_states("crude death rate in NY State", "death"), ["New York"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_mass_resolves_to_massachusetts(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES
        self.assertEqual(extract_states("uninsured rate in Mass", "insurance"), ["Massachusetts"])
        self.assertEqual(extract_states("uninsured rate in MA", "insurance"), ["Massachusetts"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_washington_dc_variants_resolve_to_district_of_columbia(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES
        self.assertEqual(
            extract_states("uninsured rate in Washington DC", "insurance"),
            ["District of Columbia"],
        )
        self.assertEqual(
            extract_states("uninsured rate in DC", "insurance"), ["District of Columbia"]
        )
        self.assertEqual(
            extract_states("uninsured rate in D.C.", "insurance"), ["District of Columbia"]
        )

    @patch("nodes.execute_tasks.get_available_states")
    def test_us_variants_resolve_to_us(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES
        for phrase in ["US", "U.S.", "USA", "United States"]:
            self.assertEqual(
                extract_states(f"uninsured rate in the {phrase}", "insurance"),
                ["US"],
                msg=f"failed for phrase: {phrase}",
            )

    @patch("nodes.execute_tasks.get_available_states")
    def test_west_virginia_matched_before_virginia_with_aliases(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES

        self.assertEqual(
            extract_states("median home price in West Virginia", "housing"), ["West Virginia"]
        )
        self.assertEqual(extract_states("median home price in WV", "housing"), ["West Virginia"])
        self.assertEqual(extract_states("median home price in VA", "housing"), ["Virginia"])
        self.assertEqual(
            extract_states("median home price in Virginia", "housing"), ["Virginia"]
        )
        self.assertEqual(
            extract_states("compare WV and VA", "housing"), ["West Virginia", "Virginia"]
        )

    @patch("nodes.execute_tasks.get_available_states")
    def test_multi_state_query_using_aliases(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES

        result = extract_states("compare the uninsured rate in CA, TX, and Mass", "insurance")

        self.assertEqual(result, ["California", "Texas", "Massachusetts"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_alias_matching_is_case_insensitive(self, mock_get_states):
        mock_get_states.return_value = self.ALL_STATES

        self.assertEqual(extract_states("uninsured rate in ca", "insurance"), ["California"])
        self.assertEqual(extract_states("uninsured rate in Ca", "insurance"), ["California"])
        self.assertEqual(extract_states("uninsured rate in usa", "insurance"), ["US"])

    @patch("nodes.execute_tasks.get_available_states")
    def test_alias_not_applied_when_canonical_state_unavailable(self, mock_get_states):
        # PA -> Pennsylvania alias should be inert if the domain's dynamic
        # state list doesn't actually include Pennsylvania.
        mock_get_states.return_value = ["Texas", "California"]

        self.assertEqual(extract_states("median home price in PA", "housing"), [])

    @patch("nodes.execute_tasks.get_available_states")
    def test_us_alias_available_even_if_state_list_is_empty(self, mock_get_states):
        mock_get_states.return_value = []

        self.assertEqual(extract_states("uninsured rate in the US", "insurance"), ["US"])


class CacheTests(unittest.TestCase):
    """Metadata caching and clear_metadata_cache()."""

    def setUp(self):
        clear_metadata_cache()

    @patch("services.data_service.clickhouse_service")
    def test_available_years_cached_across_calls(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = [
            [{"name": "y2024"}],
            [{"y2024": 53}],
        ]

        first = get_available_years("death")
        second = get_available_years("death")

        self.assertEqual(first, second)
        self.assertEqual(mock_clickhouse.query.call_count, 2)

    @patch("services.data_service.clickhouse_service")
    def test_available_states_cached_across_calls(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"area_name": "Texas"}]

        get_available_states("death")
        get_available_states("death")

        self.assertEqual(mock_clickhouse.query.call_count, 1)

    @patch("services.data_service.clickhouse_service")
    def test_clear_metadata_cache_forces_refresh(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"area_name": "Texas"}]

        get_available_states("death")
        clear_metadata_cache()
        get_available_states("death")

        self.assertEqual(mock_clickhouse.query.call_count, 2)


class GrandTotalFilterValidationTests(unittest.TestCase):
    """validate_grand_total_filters() -- literals stay hardcoded, but detectably so."""

    @patch("services.data_service.clickhouse_service")
    def test_all_filters_pass(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"n": 53}]

        self.assertEqual(validate_grand_total_filters(), {"death": True, "insurance": True})

    @patch("services.data_service.clickhouse_service")
    def test_detects_zero_matching_rows(self, mock_clickhouse):
        mock_clickhouse.query.return_value = [{"n": 0}]

        self.assertEqual(validate_grand_total_filters(), {"death": False, "insurance": False})

    @patch("services.data_service.clickhouse_service")
    def test_detects_query_error(self, mock_clickhouse):
        mock_clickhouse.query.side_effect = ClickHouseQueryError("connection refused")

        self.assertEqual(validate_grand_total_filters(), {"death": False, "insurance": False})


class ExecuteTasksYearValidationTests(unittest.TestCase):
    """Explicit-year validation against get_available_years(domain)."""

    def setUp(self):
        clear_metadata_cache()

    @patch("nodes.execute_tasks.data_service")
    @patch("nodes.execute_tasks.get_available_years")
    @patch("nodes.execute_tasks.get_available_states")
    def test_explicit_death_year_1999_is_honored(
        self, mock_get_states, mock_get_years, mock_data_service
    ):
        mock_get_states.return_value = ["Texas"]
        mock_get_years.return_value = list(range(1999, 2025))
        mock_data_service.execute.return_value = {
            "found": True,
            "domain": "death",
            "state": "Texas",
            "year": 1999,
            "metric": "Crude Rate",
            "value": 850.0,
        }

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "death",
                    "query": "Show the crude death rate in Texas in 1999",
                    "depends_on": [],
                }
            ],
        }

        output = execute_tasks(state)
        result = output["task_results"][0]["result"]

        self.assertEqual(result["year"], 1999)
        mock_data_service.execute.assert_called_once()
        self.assertEqual(mock_data_service.execute.call_args.kwargs["year"], 1999)

    @patch("nodes.execute_tasks.data_service")
    @patch("nodes.execute_tasks.get_available_years")
    @patch("nodes.execute_tasks.get_available_states")
    def test_explicit_unavailable_year_returns_clean_response(
        self, mock_get_states, mock_get_years, mock_data_service
    ):
        mock_get_states.return_value = ["Texas"]
        mock_get_years.return_value = list(range(1999, 2025))

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "death",
                    "query": "Show the crude death rate in Texas in 1800",
                    "depends_on": [],
                }
            ],
        }

        output = execute_tasks(state)
        result = output["task_results"][0]["result"]

        self.assertFalse(result["found"])
        self.assertEqual(result["year"], 1800)
        self.assertIn("1800", result["message"])
        mock_data_service.execute.assert_not_called()

    @patch("nodes.execute_tasks.data_service")
    @patch("nodes.execute_tasks.get_available_years")
    @patch("nodes.execute_tasks.get_available_states")
    def test_multi_state_comparison_outside_old_state_list(
        self, mock_get_states, mock_get_years, mock_data_service
    ):
        mock_get_states.return_value = ["Ohio", "Massachusetts"]
        mock_get_years.return_value = []
        mock_data_service.execute.side_effect = [
            {"found": True, "domain": "death", "state": "Ohio", "year": 2020, "metric": "Crude Rate", "value": 950.0},
            {"found": True, "domain": "death", "state": "Massachusetts", "year": 2020, "metric": "Crude Rate", "value": 820.0},
        ]

        state = {
            "tasks": [
                {
                    "task_id": "task_1",
                    "domain": "death",
                    "query": "Compare the death rate in Ohio and Massachusetts in 2020",
                    "depends_on": [],
                }
            ],
        }

        output = execute_tasks(state)
        result = output["task_results"][0]["result"]

        called_states = {call.kwargs["state"] for call in mock_data_service.execute.call_args_list}
        self.assertEqual(called_states, {"Ohio", "Massachusetts"})
        self.assertEqual(len(result["items"]), 2)


if __name__ == "__main__":
    unittest.main()
