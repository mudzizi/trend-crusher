import logging
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

class PortfolioManager:
    def __init__(self, exchange, config):
        self.exchange = exchange
        self.config = config
        self.db = DBManager()
        
    def get_active_count(self):
        """Returns number of currently open trades across all symbols."""
        active_df = self.db.get_active_trades()
        return len(active_df)

    def get_total_equity(self, symbol=None):
        """
        Returns total equity for a specific symbol (Allocated Seed + Accumulated PnL).
        If symbol is None, returns global seed.
        """
        if not symbol:
            return self.config.get("SEED", 10000.0)

        # 1. Get allocated seed for this symbol
        symbol_settings = self.config.get("SYMBOL_SETTINGS", {}).get(symbol, {})
        allocated_seed = symbol_settings.get("ALLOCATED_SEED", 1000.0)

        if self.config.get("DRY_RUN", True):
            # In Dry Run, calculate from symbol-specific equity history
            equity_df = self.db.get_equity_history(symbol=symbol)
            if equity_df.empty:
                return float(allocated_seed)
            return float(equity_df.iloc[-1]['balance'])
        else:
            # In Live, we still track logically to maintain isolation
            # even though the exchange wallet is shared.
            equity_df = self.db.get_equity_history(symbol=symbol)
            if equity_df.empty:
                return float(allocated_seed)
            return float(equity_df.iloc[-1]['balance'])

    def get_available_margin(self, symbol):
        """
        Returns the actual available margin. 
        In Isolated mode, it's limited by the sub-balance we manage logically.
        """
        logical_equity = self.get_total_equity(symbol)
        
        if self.config.get("DRY_RUN", True):
            return logical_equity
        else:
            try:
                # Real available margin from exchange (shared across all symbols)
                balance = self.exchange.fetch_balance()
                actual_free = float(balance['free']['USDT'])
                # We take the minimum of our logical allocation and the actual wallet free balance
                return min(logical_equity, actual_free)
            except Exception as e:
                logger.error(f"Error fetching available margin: {e}")
                return 0.0

    def calculate_order_qty(self, symbol, entry_price, sl_price):
        """
        Calculates optimal position size based on symbol-specific isolation.
        """
        # 1. Check max concurrent trades (Still a global limit)
        active_count = self.get_active_count()
        if active_count >= self.config.get("MAX_CONCURRENT_TRADES", 3):
            logger.warning(f"Portfolio limit reached ({active_count}). Skipping {symbol}")
            return 0

        # 2. Get symbol-specific equity
        equity = self.get_total_equity(symbol)
        available = self.get_available_margin(symbol)
        
        if available <= 0:
            logger.error(f"[{symbol}] No available margin.")
            return 0

        # 3. Risk-based Quantity (2% of SYMBOL equity)
        symbol_settings = self.config.get("SYMBOL_SETTINGS", {}).get(symbol, {})
        risk_pct = symbol_settings.get("RISK_PER_TRADE", 0.02)
        
        risk_amt = equity * risk_pct
        stop_dist = abs(entry_price - sl_price)
        if stop_dist == 0: return 0
        risk_qty = risk_amt / stop_dist

        # 4. Margin-based Quantity (Isolated to symbol's logical share)
        max_leverage = self.config.get("MAX_LEVERAGE", 5)
        # Use available (which is min of logical and actual wallet free)
        max_notional = available * max_leverage
        max_qty = max_notional / entry_price

        # 5. Take the minimum
        final_qty = min(risk_qty, max_qty)
        
        logger.info(f"[{symbol}] Equity: {equity:.2f} | Risk_Qty: {risk_qty:.4f} | Max_Qty: {max_qty:.4f} | Final: {final_qty:.4f}")
        
        return final_qty

    def update_balance_after_trade(self, symbol, pnl_usdt):
        """Updates symbol-specific virtual balance in DB."""
        curr_equity = self.get_total_equity(symbol)
        new_equity = curr_equity + pnl_usdt
        self.db.log_equity(new_equity, symbol=symbol)
        logger.info(f"[{symbol}] Balance updated: {curr_equity:.2f} -> {new_equity:.2f}")
