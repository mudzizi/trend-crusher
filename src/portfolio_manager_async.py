import asyncio
import logging
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

class PortfolioManagerAsync:
    """
    Asynchronous Portfolio Manager with thread-safe (async-safe) capital allocation.
    """
    def __init__(self, exchange, config):
        self.exchange = exchange
        self.config = config
        self.db = DBManager()
        self.lock = asyncio.Lock() # Ensures safe concurrent access to sub-balances

    async def get_total_equity(self, symbol=None):
        """Returns total equity for a symbol (Allocated Seed + PnL) or global total."""
        async with self.lock:
            if not symbol:
                total_pnl = self.db.get_total_pnl()
                return float(self.config.get("SEED", 10000.0)) + total_pnl

            symbol_settings = self.config.get("SYMBOL_SETTINGS", {}).get(symbol, {})
            allocated_seed = symbol_settings.get("ALLOCATED_SEED", 1000.0)

            # Check DB history for latest sub-balance
            equity_df = self.db.get_equity_history(symbol=symbol)
            if equity_df.empty:
                return float(allocated_seed)
            return float(equity_df.iloc[-1]['balance'])

    async def get_available_margin(self, symbol):
        """Returns min of logical sub-balance and actual exchange free balance."""
        logical_equity = await self.get_total_equity(symbol)
        
        if self.config.get("DRY_RUN", True):
            return logical_equity
        else:
            try:
                # Use async support for balance fetch
                balance = await self.exchange.fetch_balance()
                actual_free = float(balance['free'].get('USDT', 0.0))
                return min(logical_equity, actual_free)
            except Exception as e:
                logger.error(f"Error fetching async margin: {e}")
                return 0.0

    async def calculate_order_qty(self, symbol, entry_price, sl_price):
        """Calculates size based on isolated async-safe logic."""
        # 1. Check global trade limit
        active_trades = self.db.get_active_trades()
        if len(active_trades) >= self.config.get("MAX_CONCURRENT_TRADES", 3):
            logger.warning(f"[{symbol}] Global limit reached. Skipping.")
            return 0

        # 2. Get metrics
        equity = await self.get_total_equity(symbol)
        available = await self.get_available_margin(symbol)
        
        if available <= 0:
            logger.error(f"[{symbol}] No margin available.")
            return 0

        # 3. Risk-based Qty (2% of symbol equity)
        symbol_settings = self.config.get("SYMBOL_SETTINGS", {}).get(symbol, {})
        risk_pct = symbol_settings.get("RISK_PER_TRADE", 0.02)
        
        risk_amt = equity * risk_pct
        stop_dist = abs(entry_price - sl_price)
        if stop_dist == 0: return 0
        risk_qty = risk_amt / stop_dist

        # 4. Margin-based Qty (Leverage limit)
        max_leverage = self.config.get("MAX_LEVERAGE", 5)
        max_notional = available * max_leverage
        max_qty = max_notional / entry_price

        final_qty = min(risk_qty, max_qty)
        logger.info(f"[{symbol}] Async Sizing - Equity: {equity:.2f} | Risk_Qty: {risk_qty:.4f} | Max_Qty: {max_qty:.4f} | Final: {final_qty:.4f}")
        
        return final_qty

    async def update_balance_after_trade(self, symbol, pnl_usdt):
        """Safely updates symbol-specific virtual balance."""
        async with self.lock:
            curr_equity = await self._get_equity_no_lock(symbol)
            new_equity = curr_equity + pnl_usdt
            self.db.log_equity(new_equity, symbol=symbol)
            logger.info(f"[{symbol}] Async Ledger Updated: {curr_equity:.2f} -> {new_equity:.2f}")

    async def _get_equity_no_lock(self, symbol):
        """Internal helper to get equity without acquiring the lock again."""
        symbol_settings = self.config.get("SYMBOL_SETTINGS", {}).get(symbol, {})
        allocated_seed = symbol_settings.get("ALLOCATED_SEED", 1000.0)
        equity_df = self.db.get_equity_history(symbol=symbol)
        if equity_df.empty:
            return float(allocated_seed)
        return float(equity_df.iloc[-1]['balance'])
