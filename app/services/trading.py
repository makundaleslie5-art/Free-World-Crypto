
from threading import Lock

from app.core.database import get_connection

STARTING_BALANCE = 10_000.00

wallet = {
    "currency": "USD",
    "available_balance": STARTING_BALANCE,
    "holdings": {},
    "transactions": [],
    "mode": "simulation",
}

wallet_lock = Lock()

PRICES = {
    "BTC": 65000.00,
    "ETH": 3200.00,
    "SOL": 150.00,
    "FREE": 0.01,
}


def load_wallet():
    """Load the saved wallet and transaction history from SQLite."""
    with get_connection() as connection:
        balance_row = connection.execute(
            "SELECT available_balance FROM wallet WHERE id = 1"
        ).fetchone()

        holdings_rows = connection.execute(
            "SELECT symbol, quantity FROM holdings"
        ).fetchall()

        transaction_rows = connection.execute("""
            SELECT side, symbol, quantity, price, total
            FROM transactions
            ORDER BY id
        """).fetchall()

    if balance_row is None:
        raise RuntimeError(
            "Wallet not initialized. Initialize the database first."
        )

    wallet["available_balance"] = balance_row["available_balance"]
    wallet["holdings"] = {
        row["symbol"]: row["quantity"] for row in holdings_rows
    }
    wallet["transactions"] = [
        dict(row) for row in transaction_rows
    ]


def buy(symbol: str, quantity: float):
    symbol = symbol.upper()

    if symbol not in PRICES:
        raise ValueError("Unsupported cryptocurrency.")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    with wallet_lock:
        cost = PRICES[symbol] * quantity
        cost = round(cost, 2)

        if cost > wallet["available_balance"]:
            raise ValueError("Insufficient demo USD balance.")

        with get_connection() as connection:
            connection.execute(
                "UPDATE wallet SET available_balance = "
                "ROUND(available_balance - ?, 2) WHERE id = 1",
                (cost,),
            )

            connection.execute("""
                INSERT INTO holdings (symbol, quantity)
                VALUES (?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    quantity = quantity + excluded.quantity
            """, (symbol, quantity))

            cursor = connection.execute("""
                INSERT INTO transactions
                    (side, symbol, quantity, price, total)
                VALUES ('BUY', ?, ?, ?, ?)
            """, (symbol, quantity, PRICES[symbol], cost))

            transaction = {
                "id": cursor.lastrowid,
                "side": "BUY",
                "symbol": symbol,
                "quantity": quantity,
                "price": PRICES[symbol],
                "total": cost,
            }

        load_wallet()
        return transaction.copy()


def sell(symbol: str, quantity: float):
    symbol = symbol.upper()

    if symbol not in PRICES:
        raise ValueError("Unsupported cryptocurrency.")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    with wallet_lock:
        owned = wallet["holdings"].get(symbol, 0.0)

        if quantity > owned:
            raise ValueError("Insufficient crypto holdings.")

        proceeds = round(PRICES[symbol] * quantity, 2)
        remaining = owned - quantity

        with get_connection() as connection:
            connection.execute(
                "UPDATE wallet SET available_balance = "
                "ROUND(available_balance + ?, 2) WHERE id = 1",
                (proceeds,),
            )

            if remaining < 1e-12:
                connection.execute(
                    "DELETE FROM holdings WHERE symbol = ?", (symbol,)
                )
            else:
                connection.execute(
                    "UPDATE holdings SET quantity = ? WHERE symbol = ?",
                    (remaining, symbol),
                )

            cursor = connection.execute("""
                INSERT INTO transactions
                    (side, symbol, quantity, price, total)
                VALUES ('SELL', ?, ?, ?, ?)
            """, (symbol, quantity, PRICES[symbol], proceeds))

            transaction = {
                "id": cursor.lastrowid,
                "side": "SELL",
                "symbol": symbol,
                "quantity": quantity,
                "price": PRICES[symbol],
                "total": proceeds,
            }

        load_wallet()
        return transaction.copy()


def get_wallet():
    with wallet_lock:
        # Read the latest persisted state so the API reflects SQLite.
        load_wallet()

        return {
            **wallet,
            "holdings": wallet["holdings"].copy(),
            "transactions": [
                transaction.copy()
                for transaction in wallet["transactions"]
            ],
            "notice": "Demo funds only. No real money is held.",
        }

