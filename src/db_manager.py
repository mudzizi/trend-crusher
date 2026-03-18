import sqlite3
import pandas as pd
from datetime import datetime

class DBManager:
    def __init__(self, db_path="trades.db"):
        self.db_path = db_path
        self._create_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    side TEXT,
                    open_time DATETIME,
                    close_time DATETIME,
                    open_price REAL,
                    close_price REAL,
                    quantity REAL,
                    pnl_pct REAL,
                    pnl_usdt REAL,
                    strength REAL,
                    status TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS equity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT (datetime('now','localtime')),
                    balance REAL
                )
            """)

    def log_trade_open(self, symbol, side, price, qty, strength):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO trades (symbol, side, open_time, open_price, quantity, strength, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, side, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), price, qty, strength, 'OPEN'))

    def log_trade_close(self, price, pnl_pct, pnl_usdt):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE trades 
                SET close_time = ?, close_price = ?, pnl_pct = ?, pnl_usdt = ?, status = ?
                WHERE status = 'OPEN'
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), price, pnl_pct, pnl_usdt, 'CLOSED'))

    def log_equity(self, balance):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO equity (balance) VALUES (?)", (balance,))

    def get_trade_history(self):
        with self._get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM trades WHERE status='CLOSED'", conn)

    def get_equity_history(self):
        with self._get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM equity", conn)
