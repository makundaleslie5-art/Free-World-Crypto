from threading import Lock
from app.core.database import get_connection

STARTING_BALANCE = 10_000.00
wallet_lock = Lock()
PRICES = {
    "BTC": 65000.00, "ETH": 3200.00, "SOL": 150.00,
    "BNB": 600.00, "XRP": 0.60, "LINK": 15.00,
    "DOGE": 0.15, "ADA": 0.45, "AVAX": 35.00,
    "HYPE": 25.00, "DOT": 7.00, "LTC": 80.00,
    "TRX": 0.12, "FREE": 0.01,
}


def load_wallet(user_id: int = 1):
    with get_connection() as connection:
        balance_row = connection.execute("SELECT available_balance FROM user_wallets WHERE user_id = ?", (user_id,)).fetchone()
        holdings_rows = connection.execute("SELECT symbol, quantity FROM user_holdings WHERE user_id = ?", (user_id,)).fetchall()
        transaction_rows = connection.execute("SELECT side, symbol, quantity, price, total, created_at FROM user_transactions WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
    if balance_row is None:
        raise RuntimeError("Wallet not initialized for this user.")
    return {"currency": "USD", "available_balance": balance_row["available_balance"],
            "holdings": {row["symbol"]: row["quantity"] for row in holdings_rows},
            "transactions": [dict(row) for row in transaction_rows], "mode": "simulation"}


def buy(symbol: str, quantity: float, user_id: int = 1, price: float | None = None):
    symbol = symbol.upper()
    if symbol not in PRICES: raise ValueError("Unsupported cryptocurrency.")
    if quantity <= 0: raise ValueError("Quantity must be greater than zero.")
    execution_price = float(price if price is not None else PRICES[symbol])
    if execution_price <= 0: raise ValueError("Market price must be greater than zero.")
    with wallet_lock, get_connection() as connection:
        cost = round(execution_price * quantity, 2)
        connection.execute("BEGIN IMMEDIATE")
        balance_row = connection.execute("SELECT available_balance FROM user_wallets WHERE user_id = ?", (user_id,)).fetchone()
        if balance_row is None: raise RuntimeError("Wallet is not initialized.")
        if cost > balance_row["available_balance"]: raise ValueError("Insufficient demo USD balance.")
        connection.execute("UPDATE user_wallets SET available_balance = ROUND(available_balance - ?, 2) WHERE user_id = ?", (cost, user_id))
        connection.execute("INSERT INTO user_holdings (user_id, symbol, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity", (user_id, symbol, quantity))
        cursor = connection.execute("INSERT INTO user_transactions (user_id, side, symbol, quantity, price, total) VALUES (?, 'BUY', ?, ?, ?, ?)", (user_id, symbol, quantity, execution_price, cost))
        transaction = {"id": cursor.lastrowid, "side": "BUY", "symbol": symbol, "quantity": quantity, "price": execution_price, "total": cost}
    return transaction


def sell(symbol: str, quantity: float, user_id: int = 1, price: float | None = None):
    symbol = symbol.upper()
    if symbol not in PRICES: raise ValueError("Unsupported cryptocurrency.")
    if quantity <= 0: raise ValueError("Quantity must be greater than zero.")
    execution_price = float(price if price is not None else PRICES[symbol])
    if execution_price <= 0: raise ValueError("Market price must be greater than zero.")
    with wallet_lock, get_connection() as connection:
        proceeds = round(execution_price * quantity, 2)
        connection.execute("BEGIN IMMEDIATE")
        holding_row = connection.execute("SELECT quantity FROM user_holdings WHERE user_id = ? AND symbol = ?", (user_id, symbol)).fetchone()
        owned = holding_row["quantity"] if holding_row else 0.0
        if quantity > owned: raise ValueError("Insufficient crypto holdings.")
        remaining = owned - quantity
        connection.execute("UPDATE user_wallets SET available_balance = ROUND(available_balance + ?, 2) WHERE user_id = ?", (proceeds, user_id))
        if remaining < 1e-12:
            connection.execute("DELETE FROM user_holdings WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        else:
            connection.execute("UPDATE user_holdings SET quantity = ? WHERE user_id = ? AND symbol = ?", (remaining, user_id, symbol))
        cursor = connection.execute("INSERT INTO user_transactions (user_id, side, symbol, quantity, price, total) VALUES (?, 'SELL', ?, ?, ?, ?)", (user_id, symbol, quantity, execution_price, proceeds))
        transaction = {"id": cursor.lastrowid, "side": "SELL", "symbol": symbol, "quantity": quantity, "price": execution_price, "total": proceeds}
    return transaction


def get_wallet(user_id: int = 1):
    wallet = load_wallet(user_id)
    return {**wallet, "holdings": wallet["holdings"].copy(), "transactions": [item.copy() for item in wallet["transactions"]],
            "notice": "Demo funds only. No real money is held."}
