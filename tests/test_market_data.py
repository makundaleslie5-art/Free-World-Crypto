import unittest
from unittest.mock import patch

from app.services import market_data


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = dict(market_data._cache)
        market_data._cache.update(updated_at=0.0, prices={}, source=None)

    def tearDown(self):
        market_data._cache.clear()
        market_data._cache.update(self.original_cache)

    @patch("app.services.market_data._fetch_coingecko")
    def test_live_prices_replace_sample_prices(self, fetch):
        fetch.return_value = {"BTC": 91000.0, "ETH": 3000.0, "SOL": 180.0}
        result = market_data.get_market_snapshot(force_refresh=True)
        prices = {item["symbol"]: item for item in result["prices"]}
        self.assertEqual(result["mode"], "live")
        self.assertEqual(prices["BTC"]["price"], 91000.0)
        self.assertEqual(prices["BTC"]["price_type"], "live")
        self.assertEqual(prices["FREE"]["price_type"], "simulated")

    @patch("app.services.market_data._fetch_coingecko", side_effect=OSError("offline"))
    def test_provider_failure_is_labelled_sample_fallback(self, fetch):
        result = market_data.get_market_snapshot(force_refresh=True)
        self.assertEqual(result["mode"], "sample_fallback")
        self.assertTrue(all(item["price_type"] == "simulated" for item in result["prices"]))


if __name__ == "__main__":
    unittest.main()
