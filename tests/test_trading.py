import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import database
from app.services import trading


class TradingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_wallet.db"

        self.path_patch = patch.object(
            database, "DATABASE_PATH", self.db_path
        )
        self.path_patch.start()

        self.connection_patch = patch.object(
            trading, "get_connection", database.get_connection
        )
        self.connection_patch.start()

        database.initialize_database()
        trading.load_wallet()

    def tearDown(self):
        self.connection_patch.stop()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_buy_updates_balance_holdings_and_history(self):
        transaction = trading.buy("FREE", 100)

        wallet = trading.get_wallet()

        self.assertEqual(transaction["side"], "BUY")
        self.assertAlmostEqual(wallet["available_balance"], 9999.00)
        self.assertAlmostEqual(wallet["holdings"]["FREE"], 100)
        self.assertEqual(len(wallet["transactions"]), 1)

    def test_cannot_buy_more_than_available_balance(self):
        with self.assertRaisesRegex(ValueError, "Insufficient demo USD balance"):
            trading.buy("BTC", 1)

        wallet = trading.get_wallet()

        self.assertAlmostEqual(wallet["available_balance"], 10000.00)
        self.assertEqual(wallet["holdings"], {})
        self.assertEqual(wallet["transactions"], [])

    def test_buy_uses_latest_database_balance(self):
        with database.get_connection() as connection:
            connection.execute(
                "UPDATE wallet SET available_balance = 0 WHERE id = 1"
            )

        with self.assertRaisesRegex(ValueError, "Insufficient demo USD balance"):
            trading.buy("FREE", 1)

        with database.get_connection() as connection:
            balance = connection.execute(
                "SELECT available_balance FROM wallet WHERE id = 1"
            ).fetchone()["available_balance"]

        self.assertEqual(balance, 0)
    def test_sell_uses_latest_database_holdings(self):
        trading.buy("FREE", 100)

        with database.get_connection() as connection:
            connection.execute(
                "DELETE FROM holdings WHERE symbol = ?",
                ("FREE",),
            )

        with self.assertRaisesRegex(ValueError, "Insufficient crypto holdings"):
            trading.sell("FREE", 1)

        with database.get_connection() as connection:
            balance = connection.execute(
                "SELECT available_balance FROM wallet WHERE id = 1"
            ).fetchone()["available_balance"]

            transaction_count = connection.execute(
                "SELECT COUNT(*) FROM transactions"
            ).fetchone()[0]

        self.assertEqual(balance, 9999.00)
        self.assertEqual(transaction_count, 1)
    def test_unsupported_symbol_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported cryptocurrency"):
            trading.buy("UNKNOWN", 1)

        wallet = trading.get_wallet()

        self.assertAlmostEqual(wallet["available_balance"], 10000.00)
        self.assertEqual(wallet["holdings"], {})
        self.assertEqual(wallet["transactions"], [])
    def test_cannot_sell_more_than_owned(self):
        with self.assertRaisesRegex(ValueError, "Insufficient crypto holdings"):
            trading.sell("FREE", 1)

        wallet = trading.get_wallet()

        self.assertAlmostEqual(wallet["available_balance"], 10000.00)
        self.assertEqual(wallet["holdings"], {})
        self.assertEqual(wallet["transactions"], [])


if __name__ == "__main__":
    unittest.main()
