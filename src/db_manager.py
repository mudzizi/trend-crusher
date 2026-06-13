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
                    symbol TEXT DEFAULT 'TOTAL',
                    balance REAL
                )
            """)
            # Migration: Ensure symbol column exists for older DBs
            try:
                conn.execute("ALTER TABLE equity ADD COLUMN symbol TEXT DEFAULT 'TOTAL'")
            except:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    symbol TEXT PRIMARY KEY,
                    position INTEGER,
                    entry_price REAL,
                    quantity REAL,
                    max_price REAL,
                    min_price REAL,
                    sl_price REAL,
                    sl_order_id TEXT,
                    last_updated DATETIME DEFAULT (datetime('now','localtime'))
                )
            """)
            # Migration: Add sl_price if missing
            try:
                conn.execute("ALTER TABLE bot_state ADD COLUMN sl_price REAL DEFAULT 0")
            except: pass
            
            # Migration: Add sniper/retest order IDs
            try:
                conn.execute("ALTER TABLE bot_state ADD COLUMN sniper_order_id TEXT")
                conn.execute("ALTER TABLE bot_state ADD COLUMN retest_order_id TEXT")
            except: pass

            # New table for Real-time Monitoring (History supported)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS live_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    vol_ratio REAL,
                    adx_ratio REAL,
                    prox_ratio REAL,
                    trend_ok INTEGER,
                    signal_score REAL,
                    last_price REAL,
                    upper_band REAL,
                    lower_column REAL,
                    adx_value REAL DEFAULT 0,
                    ema_value REAL DEFAULT 0,
                    chaos_value REAL DEFAULT 0,
                    squeeze_value REAL DEFAULT 0,
                    slope_value REAL DEFAULT 0,
                    chop_value REAL DEFAULT 0,
                    last_updated DATETIME DEFAULT (datetime('now','localtime'))
                )
            """)
            
            # Migration: Add new columns if missing
            for col in ['ema_value', 'chaos_value', 'squeeze_value', 'slope_value', 'chop_value', 'adx_4h_value']:
                try:
                    conn.execute(f"ALTER TABLE live_indicators ADD COLUMN {col} REAL DEFAULT 0")
                except: pass
            
            # [NEW] Table for 1h Historical Data for Charting
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history_1h (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timestamp DATETIME,
                    close REAL,
                    ema REAL,
                    donchian_upper REAL,
                    donchian_lower REAL,
                    volume REAL,
                    adx REAL,
                    chaos REAL DEFAULT 0,
                    squeeze REAL DEFAULT 0,
                    slope REAL DEFAULT 0,
                    chop REAL DEFAULT 0,
                    UNIQUE(symbol, timestamp)
                )
            """)
            # Migration for history_1h
            for col in ['chaos', 'squeeze', 'slope', 'chop', 'adx_4h']:
                try:
                    conn.execute(f"ALTER TABLE history_1h ADD COLUMN {col} REAL DEFAULT 0")
                except: pass
            
            # [NEW] Table for Security: Blocked IPs (Temporary)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blocked_ips (
                    ip TEXT PRIMARY KEY,
                    reason TEXT,
                    blocked_at DATETIME DEFAULT (datetime('now','localtime')),
                    expires_at DATETIME
                )
            """)

            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_live_indicators_symbol ON live_indicators(symbol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_1h_symbol ON history_1h(symbol)")

    def block_ip(self, ip, reason, duration_hours=24):
        """Blocks an IP address for a specified duration."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO blocked_ips (ip, reason, blocked_at, expires_at) 
                VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime', ? || ' hours'))
            """, (ip, reason, f"{duration_hours:+}"))

    def is_ip_blocked(self, ip):
        """Checks if an IP is in the blacklist and not expired."""
        with self._get_connection() as conn:
            # First, cleanup expired blocks to keep the table lean
            conn.execute("DELETE FROM blocked_ips WHERE expires_at <= datetime('now','localtime')")
            
            df = pd.read_sql_query("SELECT ip FROM blocked_ips WHERE ip = ?", conn, params=(ip,))
            return not df.empty

    def get_blocked_ip_count(self):
        """Returns the number of currently blocked IPs."""
        with self._get_connection() as conn:
            # Cleanup first
            conn.execute("DELETE FROM blocked_ips WHERE expires_at <= datetime('now','localtime')")
            df = pd.read_sql_query("SELECT COUNT(*) as count FROM blocked_ips", conn)
            return int(df.iloc[0]['count'])

    def log_history_1h(self, symbol, timestamp, close, ema, d_upper, d_lower, vol, adx, chaos=0, squeeze=0, slope=0, chop=0, adx_4h=0):
        """Logs 1h technical snapshot. timestamp can be explicit or None for 'now'."""
        ts = timestamp if timestamp else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO history_1h (symbol, timestamp, close, ema, donchian_upper, donchian_lower, volume, adx, chaos, squeeze, slope, chop, adx_4h)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, ts, close, ema, d_upper, d_lower, vol, adx, chaos, squeeze, slope, chop, adx_4h))
            
            # Cleanup old records (keep last 120 hours = 5 days)
            conn.execute("""
                DELETE FROM history_1h 
                WHERE id NOT IN (
                    SELECT id FROM history_1h WHERE symbol = ? 
                    ORDER BY timestamp DESC LIMIT 120
                ) AND symbol = ?
            """, (symbol, symbol))

    def log_history_1h_batch(self, symbol, records):
        """Logs multiple 1h technical snapshots in a single transaction using REPLACE."""
        with self._get_connection() as conn:
            data = []
            for r in records:
                ts = r['timestamp'] if r.get('timestamp') else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                data.append((
                    symbol, ts, r['close'], r['ema'], r['d_upper'], r['d_lower'], r['volume'],
                    r['adx'], r.get('chaos', 0), r.get('squeeze', 0), r.get('slope', 0), r.get('chop', 0), r.get('adx_4h', 0)
                ))
            
            conn.executemany("""
                INSERT OR REPLACE INTO history_1h (symbol, timestamp, close, ema, donchian_upper, donchian_lower, volume, adx, chaos, squeeze, slope, chop, adx_4h)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            
            # Cleanup old records (keep last 120 hours = 5 days)
            conn.execute("""
                DELETE FROM history_1h 
                WHERE id NOT IN (
                    SELECT id FROM history_1h WHERE symbol = ? 
                    ORDER BY timestamp DESC LIMIT 120
                ) AND symbol = ?
            """, (symbol, symbol))

    def get_history_1h(self, symbol, limit=48):
        """Returns recent history for a specific symbol for charting (Chronological order)."""
        with self._get_connection() as conn:
            # Get latest N records first, then sort them ASC for the chart
            query = f"""
                SELECT * FROM (
                    SELECT * FROM history_1h 
                    WHERE symbol = ? 
                    ORDER BY timestamp DESC LIMIT ?
                ) AS sub 
                ORDER BY timestamp ASC
            """
            return pd.read_sql_query(query, conn, params=(symbol, limit))

    def update_live_status(self, symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, score, last_price, upper, lower, 
                           adx_value=0, ema_value=0, chaos_value=0, squeeze_value=0, slope_value=0, chop_value=0, adx_4h_value=0):
        with self._get_connection() as conn:
            # Insert a new record for history instead of replacing
            conn.execute("""
                INSERT INTO live_indicators 
                (symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, signal_score, last_price, upper_band, lower_column, 
                 adx_value, ema_value, chaos_value, squeeze_value, slope_value, chop_value, adx_4h_value, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            """, (symbol, vol_ratio, adx_ratio, prox_ratio, 1 if trend_ok else 0, score, last_price, upper, lower, 
                  adx_value, ema_value, chaos_value, squeeze_value, slope_value, chop_value, adx_4h_value))
            
            # Optional: Cleanup old records (keep last 200 per symbol to prevent DB bloat)
            conn.execute("""
                DELETE FROM live_indicators 
                WHERE id NOT IN (
                    SELECT id FROM live_indicators 
                    WHERE symbol = ? 
                    ORDER BY last_updated DESC LIMIT 200
                ) AND symbol = ?
            """, (symbol, symbol))

    def get_all_live_status(self):
        """Returns the latest status for each symbol."""
        with self._get_connection() as conn:
            return pd.read_sql_query("""
                SELECT * FROM live_indicators 
                WHERE id IN (SELECT MAX(id) FROM live_indicators GROUP BY symbol)
            """, conn)

    def save_bot_state(self, symbol, position, entry_price, quantity, max_price, min_price, sl_price, sl_order_id, sniper_id=None, retest_id=None):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO bot_state (symbol, position, entry_price, quantity, max_price, min_price, sl_price, sl_order_id, sniper_order_id, retest_order_id, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            """, (symbol, position, entry_price, quantity, max_price, min_price, sl_price, sl_order_id, sniper_id, retest_id))

    def get_bot_state(self, symbol):
        with self._get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM bot_state WHERE symbol = ?", conn, params=(symbol,))
            return df.iloc[0].to_dict() if not df.empty else None

    def log_trade_open(self, symbol, side, price, qty, strength):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO trades (symbol, side, open_time, open_price, quantity, strength, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, side, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), price, qty, strength, 'OPEN'))

    def log_trade_close(self, symbol, price, pnl_pct, pnl_usdt):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE trades 
                SET close_time = ?, close_price = ?, pnl_pct = ?, pnl_usdt = ?, status = ?
                WHERE status = 'OPEN' AND symbol = ?
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), price, pnl_pct, pnl_usdt, 'CLOSED', symbol))

    def get_active_trades(self):
        with self._get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM trades WHERE status='OPEN'", conn)

    def log_equity(self, balance, symbol='TOTAL'):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO equity (balance, symbol) VALUES (?, ?)", (balance, symbol))

    def get_trade_history(self):
        with self._get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM trades WHERE status='CLOSED'", conn)

    def get_equity_history(self, symbol=None):
        with self._get_connection() as conn:
            query = "SELECT * FROM equity"
            params = ()
            if symbol:
                query += " WHERE symbol = ?"
                params = (symbol,)
            return pd.read_sql_query(query, conn, params=params)

    def get_total_pnl(self):
        with self._get_connection() as conn:
            df = pd.read_sql_query("SELECT SUM(pnl_usdt) as total_pnl FROM trades WHERE status='CLOSED'", conn)
            return float(df.iloc[0]['total_pnl']) if not df.empty and df.iloc[0]['total_pnl'] is not None else 0.0
