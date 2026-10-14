import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "free_world.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS wallet (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                available_balance REAL NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                symbol TEXT PRIMARY KEY,
                quantity REAL NOT NULL CHECK (quantity >= 0)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                side TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                total REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            INSERT OR IGNORE INTO wallet (id, available_balance)
            VALUES (1, 10000.00)
        """)
