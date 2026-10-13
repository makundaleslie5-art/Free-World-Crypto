
from threading import Lock

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


def buy(symbol: str, quantity: float):
    symbol = symbol.upper()

    if symbol not in PRICES:
        raise ValueError("Unsupported cryptocurrency.")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    with wallet_lock:
        cost = PRICES[symbol] * quantity

        if cost > wallet["available_balance"]:
            raise ValueError("Insufficient demo USD balance.")

        wallet["available_balance"] = round(
            wallet["available_balance"] - cost, 2
        )

        holdings = wallet["holdings"]
        holdings[symbol] = holdings.get(symbol, 0.0) + quantity

        transaction = {
            "side": "BUY",
            "symbol": symbol,
            "quantity": quantity,
            "price": PRICES[symbol],
            "total": round(cost, 2),
        }

        wallet["transactions"].append(transaction)
        return transaction.copy()


def sell(symbol: str, quantity: float):
    symbol = symbol.upper()

    if symbol not in PRICES:
        raise ValueError("Unsupported cryptocurrency.")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    with wallet_lock:
        holdings = wallet["holdings"]
        owned = holdings.get(symbol, 0.0)

        if quantity > owned:
            raise ValueError("Insufficient crypto holdings.")

        proceeds = PRICES[symbol] * quantity
        remaining = owned - quantity

        if remaining < 1e-12:
            holdings.pop(symbol, None)
        else:
            holdings[symbol] = remaining

        wallet["available_balance"] = round(
            wallet["available_balance"] + proceeds, 2
        )

        transaction = {
            "side": "SELL",
            "symbol": symbol,
            "quantity": quantity,
            "price": PRICES[symbol],
            "total": round(proceeds, 2),
        }

        wallet["transactions"].append(transaction)
        return transaction.copy()


def get_wallet():
    with wallet_lock:
        return {
            **wallet,
            "holdings": wallet["holdings"].copy(),
            "transactions": [
                transaction.copy()
                for transaction in wallet["transactions"]
            ],
            "notice": "Demo funds only. No real money is held.",
        }

