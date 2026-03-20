import logging
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

class PortfolioManager:
    def __init__(self, exchange, config):
        self.exchange = exchange
        self.config = config
        self.db = DBManager()
        
    def get_total_equity(self):
        """Returns total equity in USDT."""
        if self.config.get("DRY_RUN", True):
            # In Dry Run, get latest balance from DB
            equity_df = self.db.get_equity_history()
            if equity_df.empty:
                return self.config.get("SEED", 10000.0)
            return float(equity_df.iloc[-1]['balance'])
        else:
            # In Live mode, fetch from exchange
            try:
                balance = self.exchange.fetch_balance()
                return float(balance['total']['USDT'])
            except Exception as e:
                logger.error(f"Error fetching balance from exchange: {e}")
                # Fallback to config seed or 0 if error
                return self.config.get("SEED", 0.0)

    def get_active_count(self):
        """Returns number of currently open trades."""
        if self.config.get("DRY_RUN", True):
            active_df = self.db.get_active_trades()
            return len(active_df)
        else:
            # In Live, we could check active positions via exchange
            # But relying on DB for cross-bot state might be easier for now
            # if multiple instances are running.
            active_df = self.db.get_active_trades()
            return len(active_df)

    def get_available_margin(self):
        """Returns the actual available margin (free collateral) in USDT."""
        if self.config.get("DRY_RUN", True):
            return self.get_total_equity()
        else:
            try:
                balance = self.exchange.fetch_balance()
                # 'free' represents the margin available for new orders
                return float(balance['free']['USDT'])
            except Exception as e:
                logger.error(f"Error fetching available margin: {e}")
                return 0.0

    def calculate_order_qty(self, symbol, entry_price, sl_price):
        """
        Calculates optimal position size based on risk and margin constraints.
        """
        # 1. Check max concurrent trades
        active_count = self.get_active_count()
        if active_count >= self.config.get("MAX_CONCURRENT_TRADES", 3):
            logger.warning(f"Portfolio limit reached ({active_count}/{self.config.get('MAX_CONCURRENT_TRADES')}). Skipping {symbol}")
            return 0

        # 2. Get total equity & available margin
        equity = self.get_total_equity()
        available_margin = self.get_available_margin()
        
        if available_margin <= 0:
            logger.error("No available margin to open new position.")
            return 0

        # 3. Risk-based Quantity (Still based on total equity for consistent risk management)
        symbol_settings = self.config.get("SYMBOL_SETTINGS", {}).get(symbol, {})
        risk_pct = symbol_settings.get("RISK_PER_TRADE", self.config.get("RISK_PER_TRADE", 0.02))
        
        risk_amt = equity * risk_pct
        stop_dist = abs(entry_price - sl_price)
        if stop_dist == 0: return 0
        risk_qty = risk_amt / stop_dist

        # 4. Margin-based Quantity (Double constraint: Weight vs Available Margin)
        symbol_weights = self.config.get("SYMBOL_WEIGHTS", {})
        default_weight = 1.0 / self.config.get("MAX_CONCURRENT_TRADES", 3)
        weight = symbol_weights.get(symbol, default_weight)
        
        max_leverage = self.config.get("MAX_LEVERAGE", 5)
        # Allocate based on weight but cap by actual available margin
        allocated_capital = min(equity * weight, available_margin)
        
        max_notional = allocated_capital * max_leverage
        max_qty = max_notional / entry_price

        # 5. Take the minimum of both
        final_qty = min(risk_qty, max_qty)
        
        logger.info(f"[{symbol}] Equity: {equity:.2f} | Available: {available_margin:.2f} | Risk_Qty: {risk_qty:.4f} | Max_Qty: {max_qty:.4f} | Final: {final_qty:.4f}")
        
        return final_qty

    def update_balance_after_trade(self, pnl_usdt):
        """Updates virtual balance in DB after a trade closes (Dry Run only)."""
        if self.config.get("DRY_RUN", True):
            curr_equity = self.get_total_equity()
            new_equity = curr_equity + pnl_usdt
            self.db.log_equity(new_equity)
            logger.info(f"Updated virtual balance: {curr_equity:.2f} -> {new_equity:.2f}")
