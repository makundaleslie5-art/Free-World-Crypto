import unittest

from app.services.simulation import FreeMarketSimulator


class FixedRandom:
    def gauss(self, mean, deviation):
        return 0.0

    def uniform(self, low, high):
        return 1.0

    def randint(self, low, high):
        return 1


class FreeMarketSimulationTests(unittest.TestCase):
    def setUp(self):
        self.market = FreeMarketSimulator(rng=FixedRandom())

    def test_initial_price_is_correct(self):
        snapshot = self.market.get_snapshot()
        self.assertEqual(snapshot["price"], 0.01)
        self.assertEqual(snapshot["symbol"], "FREE")

    def test_market_tick_creates_price_history(self):
        self.market.tick()
        snapshot = self.market.get_snapshot()

        self.assertEqual(len(snapshot["history"]), 2)
        self.assertGreater(snapshot["session_volume"], 0)

    def test_buy_pressure_increases_price(self):
        initial_price = self.market.get_snapshot()["price"]

        self.market.record_trade("BUY", 100)
        self.market.tick()

        new_price = self.market.get_snapshot()["price"]
        self.assertGreater(new_price, initial_price)

    def test_sell_pressure_decreases_price(self):
        initial_price = self.market.get_snapshot()["price"]

        self.market.record_trade("SELL", 100)
        self.market.tick()

        new_price = self.market.get_snapshot()["price"]
        self.assertLess(new_price, initial_price)

    def test_invalid_trade_is_rejected(self):
        with self.assertRaises(ValueError):
            self.market.record_trade("UNKNOWN", 10)

        with self.assertRaises(ValueError):
            self.market.record_trade("BUY", -10)


if __name__ == "__main__":
    unittest.main()
