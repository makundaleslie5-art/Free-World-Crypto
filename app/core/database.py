import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "free_world.db"


@contextmanager
def get_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        # Legacy tables are retained so existing installations can be upgraded safely.
        connection.execute("CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY CHECK (id = 1), available_balance REAL NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS holdings (symbol TEXT PRIMARY KEY, quantity REAL NOT NULL CHECK (quantity >= 0))")
        connection.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, side TEXT NOT NULL, symbol TEXT NOT NULL, quantity REAL NOT NULL, price REAL NOT NULL, total REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        connection.execute("INSERT OR IGNORE INTO wallet (id, available_balance) VALUES (1, 10000.00)")

        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            login_password_hash TEXT NOT NULL,
            funds_password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS user_wallets (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            available_balance REAL NOT NULL CHECK (available_balance >= 0),
            currency TEXT NOT NULL DEFAULT 'USD'
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS user_holdings (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL CHECK (quantity >= 0),
            PRIMARY KEY (user_id, symbol)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS user_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            side TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        # A reserved legacy/demo account preserves old data and the original unit-test behavior.
        connection.execute("""INSERT OR IGNORE INTO users (id, email, login_password_hash, funds_password_hash)
            VALUES (1, 'demo@freeworld.local', 'legacy-disabled', 'legacy-disabled')""")
        connection.execute("INSERT OR IGNORE INTO user_wallets (user_id, available_balance) SELECT 1, available_balance FROM wallet WHERE id=1")
        connection.execute("INSERT OR IGNORE INTO user_holdings (user_id, symbol, quantity) SELECT 1, symbol, quantity FROM holdings")
        legacy_count = connection.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()["count"]
        demo_count = connection.execute("SELECT COUNT(*) AS count FROM user_transactions WHERE user_id = 1").fetchone()["count"]
        if legacy_count and not demo_count:
            connection.execute("INSERT INTO user_transactions (user_id, side, symbol, quantity, price, total, created_at) SELECT 1, side, symbol, quantity, price, total, created_at FROM transactions")
