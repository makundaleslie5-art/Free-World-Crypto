import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.core import database
from app.main import app


class AuthAndWalletTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth_test.db"
        self.path_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.path_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()



    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.path_patch.stop()
        self.temp_dir.cleanup()



    def register(self, email="alice@example.com"):
        return self.client.post("/auth/register", json={
            "email": email,
            "login_password": "LoginPassword123",
            "funds_password": "SeparateFundsPass123",
        })



    def test_register_and_wallet_isolated(self):
        response = self.register()
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        wallet_before = self.client.get("/wallet", headers=headers).json()
        self.assertEqual(wallet_before["available_balance"], 10000)
        trade = self.client.post("/trade/buy", headers=headers, json={
            "symbol": "FREE", "quantity": 100, "funds_password": "SeparateFundsPass123"
        })
        self.assertEqual(trade.status_code, 200, trade.text)
        wallet_after = self.client.get("/wallet", headers=headers).json()
        self.assertEqual(wallet_after["available_balance"], 9999)
        self.assertEqual(wallet_after["holdings"]["FREE"], 100)
        # Reserved legacy wallet should not be affected by this new user's trade.
        with database.get_connection() as connection:
            legacy_wallet = connection.execute("SELECT available_balance FROM user_wallets WHERE user_id=1").fetchone()
        self.assertEqual(legacy_wallet["available_balance"], 10000)



    def test_wrong_funds_password_is_rejected(self):
        response = self.register()
        headers = {"Authorization": f"Bearer {response.json()['token']}"}
        trade = self.client.post("/trade/buy", headers=headers, json={
            "symbol": "FREE", "quantity": 100, "funds_password": "WrongFundsPassword"
        })
        self.assertEqual(trade.status_code, 403)



    def test_duplicate_email_rejected(self):
        self.assertEqual(self.register().status_code, 200)
        duplicate = self.register()
        self.assertEqual(duplicate.status_code, 409)



    def test_wallet_requires_login(self):
        response = self.client.get("/wallet")
        self.assertEqual(response.status_code, 401)



if __name__ == "__main__":
    unittest.main()
