import unittest
from unittest.mock import patch

from services.data_service import data_service


class InsuranceMockTests(unittest.TestCase):
    """insurance keeps using mock data; its ClickHouse table is empty."""

    def test_execute_returns_known_mock_value(self):
        result = data_service.execute(domain="insurance", state="Texas", year=2022)

        self.assertTrue(result["found"])
        self.assertEqual(result["uninsured_rate"], 16.6)

    def test_execute_does_not_touch_clickhouse(self):
        with patch("services.data_service.clickhouse_service") as mock_clickhouse:
            data_service.execute(domain="insurance", state="California", year=2022)
            mock_clickhouse.query.assert_not_called()

    def test_rank_returns_mock_ranking(self):
        results = data_service.rank(domain="insurance", year=2022, top_n=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["state"], "Texas")  # highest uninsured_rate

    def test_unknown_state_year_not_found(self):
        result = data_service.execute(domain="insurance", state="Texas", year=1999)
        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
