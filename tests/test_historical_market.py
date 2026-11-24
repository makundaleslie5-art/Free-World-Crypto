import unittest
from unittest.mock import patch

from app.services import historical_market


class HistoricalMarketTests(unittest.TestCase):
    def setUp(self):
        historical_market.clear_chart_cache()

    def tearDown(self):
        historical_market.clear_chart_cache()

    @patch("app.services.historical_market._get_json")
    def test_returns_real_ohlc_and_volume_snapshots(self, get_json):
        get_json.side_effect = [
            [[100000, 10, 12, 9, 11], [130000, 11, 13, 10, 12]],
            {"total_volumes": [[100000, 1000], [130000, 1100]]},
        ]
        result = historical_market.get_historical_chart("BTC", force_refresh=True)
        self.assertEqual(result["source"], "CoinGecko")
        self.assertEqual(result["granularity"], "30m")
        self.assertEqual(result["candles"][0]["open"], 10.0)
        self.assertEqual(result["candles"][1]["close"], 12.0)
        self.assertEqual(result["volume_snapshots"][1]["volume_24h"], 1100.0)
        self.assertEqual(get_json.call_count, 2)

    @patch("app.services.historical_market._get_json")
    def test_market_overview_returns_change_cap_and_volume(self, get_json):
        get_json.return_value = [{
            "id": "bitcoin", "current_price": 100000,
            "price_change_percentage_24h": 2.5,
            "market_cap": 1_900_000_000_000,
            "total_volume": 40_000_000_000, "market_cap_rank": 1,
        }]
        result = historical_market.get_market_overview(force_refresh=True)
        self.assertEqual(result["assets"]["BTC"]["price_change_24h_pct"], 2.5)
        self.assertEqual(result["assets"]["BTC"]["market_cap"], 1_900_000_000_000)
        self.assertEqual(result["assets"]["BTC"]["volume_24h"], 40_000_000_000)

    def test_free_is_not_misrepresented_as_listed_coin(self):
        with self.assertRaisesRegex(ValueError, "FREE is a simulated"):
            historical_market.get_historical_chart("FREE")

    @patch("app.services.historical_market._get_json")
    def test_chart_response_is_cached(self, get_json):
        get_json.side_effect = [
            [[100000, 10, 12, 9, 11], [130000, 11, 13, 10, 12]],
            {"total_volumes": [[100000, 1000]]},
        ]
        first = historical_market.get_historical_chart("ETH")
        second = historical_market.get_historical_chart("ETH")
        self.assertEqual(first["cache"], "miss")
        self.assertEqual(second["cache"], "hit")
        self.assertEqual(get_json.call_count, 2)


if __name__ == "__main__":
    unittest.main()
