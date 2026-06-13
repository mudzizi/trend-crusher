import asyncio
from src.db_manager import DBManager

class AsyncDBManager:
    """
    Asynchronous wrapper for DBManager to prevent blocking of the event loop
    during database I/O operations. Uses asyncio.to_thread to delegate DB calls
    to a background thread pool.
    """
    def __init__(self, db_path="trades.db"):
        self.db = DBManager(db_path=db_path)

    async def block_ip(self, ip, reason, duration_hours=24):
        return await asyncio.to_thread(self.db.block_ip, ip, reason, duration_hours)

    async def is_ip_blocked(self, ip):
        return await asyncio.to_thread(self.db.is_ip_blocked, ip)

    async def get_blocked_ip_count(self):
        return await asyncio.to_thread(self.db.get_blocked_ip_count)

    async def log_history_1h(self, symbol, timestamp, close, ema, d_upper, d_lower, vol, adx, chaos=0, squeeze=0, slope=0, chop=0, adx_4h=0):
        return await asyncio.to_thread(
            self.db.log_history_1h,
            symbol, timestamp, close, ema, d_upper, d_lower, vol, adx, chaos, squeeze, slope, chop, adx_4h
        )

    async def log_history_1h_batch(self, symbol, records):
        return await asyncio.to_thread(self.db.log_history_1h_batch, symbol, records)

    async def get_history_1h(self, symbol, limit=48):
        return await asyncio.to_thread(self.db.get_history_1h, symbol, limit)

    async def update_live_status(self, symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, score, last_price, upper, lower, 
                                 adx_value=0, ema_value=0, chaos_value=0, squeeze_value=0, slope_value=0, chop_value=0, adx_4h_value=0):
        return await asyncio.to_thread(
            self.db.update_live_status,
            symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, score, last_price, upper, lower,
            adx_value, ema_value, chaos_value, squeeze_value, slope_value, chop_value, adx_4h_value
        )

    async def get_all_live_status(self):
        return await asyncio.to_thread(self.db.get_all_live_status)

    async def save_bot_state(self, symbol, position, entry_price, quantity, max_price, min_price, sl_price, sl_order_id, sniper_id=None, retest_id=None):
        return await asyncio.to_thread(
            self.db.save_bot_state,
            symbol, position, entry_price, quantity, max_price, min_price, sl_price, sl_order_id, sniper_id, retest_id
        )

    async def get_bot_state(self, symbol):
        return await asyncio.to_thread(self.db.get_bot_state, symbol)

    async def log_trade_open(self, symbol, side, price, qty, strength):
        return await asyncio.to_thread(self.db.log_trade_open, symbol, side, price, qty, strength)

    async def log_trade_close(self, symbol, price, pnl_pct, pnl_usdt):
        return await asyncio.to_thread(self.db.log_trade_close, symbol, price, pnl_pct, pnl_usdt)

    async def get_active_trades(self):
        return await asyncio.to_thread(self.db.get_active_trades)

    async def log_equity(self, balance, symbol='TOTAL'):
        return await asyncio.to_thread(self.db.log_equity, balance, symbol)

    async def get_trade_history(self):
        return await asyncio.to_thread(self.db.get_trade_history)

    async def get_equity_history(self, symbol=None):
        return await asyncio.to_thread(self.db.get_equity_history, symbol)

    async def get_total_pnl(self):
        return await asyncio.to_thread(self.db.get_total_pnl)
