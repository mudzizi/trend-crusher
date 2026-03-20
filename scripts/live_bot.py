import ccxt
import time
import pandas as pd
import os
import logging
from datetime import datetime
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.risk import calculate_position_size as shared_calculate_position_size
from src.symbol_defaults import apply_symbol_defaults
from src.telegram_utils import TelegramNotifier
from src.db_manager import DBManager
from src.visualizer import TradingVisualizer

# --- Logging Setup ---
os.makedirs("log", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("log/live_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

class TrendCrusherLive:
    def __init__(self):
        CONFIG.update(apply_symbol_defaults(CONFIG, CONFIG["SYMBOL"]))
        self.exchange = ccxt.binance({
            'apiKey': CONFIG["BINANCE_API_KEY"],
            'secret': CONFIG["BINANCE_SECRET"],
            'options': {'defaultType': 'future'},
            'enableRateLimit': True
        })
        self.notifier = TelegramNotifier()
        self.db = DBManager()
        self.viz = TradingVisualizer()
        self.symbol = CONFIG["SYMBOL"]
        
        # Load markets for precision and limits
        try:
            self.exchange.load_markets()
            logger.info(f"Market data loaded for {self.symbol}")
        except Exception as e:
            logger.error(f"Error loading markets: {e}")
        
        self.session_capital = CONFIG["SEED"]
        self.initial_seed = CONFIG["SEED"]
        
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.last_entry_time = pd.Timestamp.min
        self.next_split_time = None
        self.splits_filled = 0
        
        self.db.log_equity(self.session_capital)
        
        logger.info("="*50)
        logger.info(f"🚀 TrendCrusher Live Bot Started")
        logger.info(f"Mode: {'DRY RUN' if CONFIG['DRY_RUN'] else 'LIVE'}")
        logger.info(f"Symbol: {self.symbol} | Seed: {self.initial_seed} USDT")
        logger.info(f"Splits: {CONFIG['ENTRY_SPLIT_COUNT']}")
        logger.info(f"Trend TF: {CONFIG['TREND_TIMEFRAME']} | EMA: {CONFIG['EMA_TREND_PERIOD']}")
        logger.info("="*50)
        self.notifier.notify_status(f"Bot V3 Started on {self.symbol}. Seed: {self.initial_seed} USDT")

    def fetch_data(self, tf, limit=250):
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def calculate_indicators(self):
        df_1h = self.fetch_data(CONFIG["SIGNAL_TIMEFRAME"])
        df_4h = self.fetch_data(CONFIG["TREND_TIMEFRAME"])
        
        df_1h['upper'], df_1h['lower'] = calculate_donchian(df_1h, CONFIG["DONCHIAN_PERIOD"])
        df_1h['atr'] = calculate_atr(df_1h, CONFIG["ATR_PERIOD"])
        df_1h['avg_vol'] = calculate_avg_vol(df_1h, CONFIG["AVG_VOL_PERIOD"])
        
        ema_4h = calculate_ema(df_4h, CONFIG["EMA_TREND_PERIOD"])
        
        return df_1h, ema_4h.iloc[-1]

    def split_count(self):
        return max(int(CONFIG.get("ENTRY_SPLIT_COUNT", 1)), 1)

    def split_risk_pct(self):
        return CONFIG["RISK_PER_TRADE"] / self.split_count()

    def _build_fill_result(self, success, price=0.0, quantity=0.0, order=None):
        price = float(price or 0.0)
        quantity = float(quantity or 0.0)
        return {
            "success": success,
            "price": price,
            "quantity": quantity,
            "cost": price * quantity,
            "order": order,
        }

    def _extract_fill_from_order(self, order, fallback_price, fallback_qty):
        if not order:
            return self._build_fill_result(False, fallback_price, fallback_qty, order)

        average_price = order.get("average") or order.get("price")
        filled_qty = order.get("filled") or order.get("amount")
        cost = order.get("cost")

        if (average_price is None or float(average_price or 0) <= 0) and cost and filled_qty:
            average_price = float(cost) / float(filled_qty)

        if average_price is None or float(average_price or 0) <= 0:
            average_price = fallback_price
        if filled_qty is None or float(filled_qty or 0) <= 0:
            filled_qty = fallback_qty

        fill = self._build_fill_result(True, average_price, filled_qty, order)
        if cost:
            fill["cost"] = float(cost)
        return fill

    def _resolve_market_fill(self, order, fallback_price, fallback_qty):
        fill = self._extract_fill_from_order(order, fallback_price, fallback_qty)
        order_id = order.get("id") if order else None
        has_fetch_order = bool(getattr(self.exchange, "has", {}).get("fetchOrder"))
        needs_refresh = order_id and (
            float(order.get("average") or 0) <= 0 or float(order.get("filled") or 0) <= 0
        )

        if needs_refresh and has_fetch_order:
            try:
                refreshed_order = self.exchange.fetch_order(order_id, self.symbol)
                refreshed_fill = self._extract_fill_from_order(refreshed_order, fallback_price, fallback_qty)
                if refreshed_fill["quantity"] > 0:
                    return refreshed_fill
            except Exception as e:
                logger.warning(f"Order fill refresh failed for {order_id}: {e}")
        return fill

    def _can_add_split(self, signal_time, price, trend_value):
        if self.position == 0 or self.splits_filled >= self.split_count() or self.next_split_time is None:
            return False
        if signal_time < self.next_split_time:
            return False
        if self.position == 1:
            return price > trend_value
        return price < trend_value

    def _record_entry_fill(self, direction, price, filled_qty, previous_qty, signal_time, strength, is_add):
        if filled_qty <= 0:
            return False

        side = "LONG" if direction == 1 else "SHORT"
        total_qty = previous_qty + filled_qty
        weighted_notional = (self.entry_price * previous_qty) + (price * filled_qty)
        self.quantity = total_qty
        self.entry_price = weighted_notional / total_qty
        self.position = direction
        self.last_entry_time = signal_time
        self.splits_filled += 1
        if self.splits_filled < self.split_count():
            self.next_split_time = signal_time + pd.to_timedelta(CONFIG["SIGNAL_TIMEFRAME"])
        else:
            self.next_split_time = None

        if previous_qty > 0:
            self.max_price_seen = max(self.max_price_seen, price)
            self.min_price_seen = min(self.min_price_seen, price)
            self.db.update_open_trade(self.entry_price, self.quantity, strength)
            logger.info(
                f"➕ Added split {self.splits_filled}/{self.split_count()} at {price:,.2f} "
                f"| Avg Entry: {self.entry_price:,.2f} | Qty: {self.quantity}"
            )
            self.notifier.notify_status(
                f"{self.symbol} {side} split {self.splits_filled}/{self.split_count()} added at "
                f"{price:,.2f}. Avg entry {self.entry_price:,.2f}"
            )
        else:
            self.max_price_seen = price
            self.min_price_seen = price
            self.db.log_trade_open(self.symbol, side, self.entry_price, self.quantity, strength)
            self.notifier.notify_entry(side, price, self.sl_price, strength)

        return True

    def _reset_position_state(self):
        self.position = 0
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.last_entry_time = pd.Timestamp.min
        self.next_split_time = None
        self.splits_filled = 0

    def run(self):
        while True:
            try:
                df_1h, ema_4h_val = self.calculate_indicators()
                row = df_1h.iloc[-1]
                signal_time = pd.to_datetime(row['timestamp'])
                ticker = self.exchange.fetch_ticker(self.symbol)
                c_close = float(ticker['last'])
                
                upper = row['upper']
                lower = row['lower']
                atr = row['atr']
                curr_vol = row['volume']
                avg_vol = row['avg_vol']
                vol_ratio = curr_vol / (avg_vol + 1e-10)
                trend_status = "BULL" if c_close > ema_4h_val else "BEAR"

                # Log to both console and file
                logger.info(f"Price: {c_close:,.2f} | Session Cap: {self.session_capital:,.2f} | Pos: {self.position}")
                logger.info(f"  Trend: {trend_status} | Vol: {vol_ratio:.2f}x | ST: Up {upper:,.2f} / Dn {lower:,.2f}")
                
                if self.position != 0:
                    pnl_now = ((c_close / self.entry_price) - 1) * 100 * self.position
                    
                    # --- Calculate Current Active SL (Initial vs Trailing) ---
                    if self.position == 1:
                        self.max_price_seen = max(self.max_price_seen, c_close)
                        trail_sl = self.max_price_seen - (atr * CONFIG["TRAILING_ATR_MULT"])
                        active_sl = max(self.sl_price, trail_sl)
                        sl_type = "TP" if active_sl > self.entry_price else "SL"
                    else:
                        self.min_price_seen = min(self.min_price_seen, c_close)
                        trail_sl = self.min_price_seen + (atr * CONFIG["TRAILING_ATR_MULT"])
                        active_sl = min(self.sl_price, trail_sl)
                        sl_type = "TP" if active_sl < self.entry_price else "SL"

                    logger.info(f"  Current PnL: {pnl_now:+.2f}% | Entry: {self.entry_price:,.2f} | {sl_type}: {active_sl:,.2f}")

                # --- MONITORING EXIT ---
                if self.position != 0:
                    should_exit = False
                    if self.position == 1:
                        if c_close <= active_sl: should_exit = True
                    else:
                        if c_close >= active_sl: should_exit = True
                    
                    if should_exit:
                        pre_exit_qty = self.quantity
                        exit_fill = self.execute_order(0, c_close)
                        if not exit_fill["success"] or exit_fill["quantity"] <= 0:
                            logger.error("Exit fill unavailable; keeping position state unchanged.")
                            continue

                        exit_price = exit_fill["price"]
                        filled_qty = min(exit_fill["quantity"], pre_exit_qty)
                        pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
                        gross_pnl_usdt = (exit_price - self.entry_price) * filled_qty * self.position
                        fee_usdt = (self.entry_price * filled_qty * CONFIG["FEE_RATE"]) + (exit_price * filled_qty * CONFIG["FEE_RATE"])
                        actual_pnl_usdt = gross_pnl_usdt - fee_usdt
                        
                        logger.info(f"🛑 EXIT SIGNAL: Closing at {exit_price:,.2f} | PnL: {actual_pnl_usdt:+.2f} USDT")
                        self.session_capital += actual_pnl_usdt
                        self.db.log_equity(self.session_capital)

                        if filled_qty >= pre_exit_qty - 1e-9:
                            self.db.log_trade_close(exit_price, pnl_pct, actual_pnl_usdt)
                            self.viz.generate_report(df_1h, self.db.get_trade_history(), self.db.get_equity_history(), self.symbol)
                            self.notifier.notify_exit("AUTO_EXIT", exit_price, pnl_pct, actual_pnl_usdt)
                            self._reset_position_state()
                        else:
                            self.quantity = pre_exit_qty - filled_qty
                            self.db.update_open_trade(self.entry_price, self.quantity)
                            logger.warning(
                                f"Partial exit detected: filled {filled_qty}, remaining {self.quantity}. "
                                f"Keeping position open."
                            )
                            self.notifier.notify_status(
                                f"{self.symbol} partial exit filled {filled_qty:.6f} at {exit_price:,.2f}. "
                                f"Remaining qty {self.quantity:.6f}"
                            )

                # --- MONITORING ENTRY ---
                strength = min(100, vol_ratio * 50)
                if self.position != 0 and self._can_add_split(signal_time, c_close, ema_4h_val):
                    prev_qty = self.quantity
                    fill = self.execute_order(self.position, c_close, risk_pct=self.split_risk_pct())
                    self._record_entry_fill(self.position, fill["price"], fill["quantity"], prev_qty, signal_time, strength, is_add=True)
                elif self.position == 0:
                    is_vol_burst = curr_vol > (avg_vol * CONFIG["VOL_MULTIPLIER"])
                    
                    if is_vol_burst and c_close > ema_4h_val and c_close > upper:
                        logger.info(f"🚀 BUY SIGNAL: Price {c_close:,.2f} > Upper {upper:,.2f}")
                        self.sl_price = c_close - (atr * CONFIG["INITIAL_SL_ATR"])
                        fill = self.execute_order(1, c_close, risk_pct=self.split_risk_pct())
                        self._record_entry_fill(1, fill["price"], fill["quantity"], 0, signal_time, strength, is_add=False)
                        
                    elif is_vol_burst and c_close < ema_4h_val and c_close < lower:
                        logger.info(f"📉 SELL SIGNAL: Price {c_close:,.2f} < Lower {lower:,.2f}")
                        self.sl_price = c_close + (atr * CONFIG["INITIAL_SL_ATR"])
                        fill = self.execute_order(-1, c_close, risk_pct=self.split_risk_pct())
                        self._record_entry_fill(-1, fill["price"], fill["quantity"], 0, signal_time, strength, is_add=False)

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                self.notifier.notify_error(str(e))
            
            time.sleep(CONFIG["LOOP_INTERVAL"])

    def execute_order(self, direction, price, risk_pct=None):
        if direction == 0:
            fallback_qty = self.quantity
            if not CONFIG["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                try:
                    order = self.exchange.create_market_order(self.symbol, side, self.quantity)
                    fill = self._resolve_market_fill(order, price, fallback_qty)
                    logger.info(f"✅ Closed Position: {side} {fill['quantity']} @ {fill['price']:,.2f}")
                    return fill
                except Exception as e:
                    logger.error(f"❌ Exit Order Failed: {e}")
                    return self._build_fill_result(False, price, 0.0)
            return self._build_fill_result(True, price, fallback_qty)
        else:
            # 1. Calculate Risk-based Quantity
            stop_dist = abs(price - self.sl_price)
            if stop_dist == 0:
                return self._build_fill_result(False, price, 0.0)

            risk_pct = CONFIG["RISK_PER_TRADE"] if risk_pct is None else risk_pct

            raw_qty = shared_calculate_position_size(
                capital=self.session_capital,
                price=price,
                stop_loss_price=self.sl_price,
                risk_pct=risk_pct,
                max_leverage=CONFIG.get("MAX_LEVERAGE"),
                max_trade_loss_pct_cap=CONFIG.get("MAX_TRADE_LOSS_PCT_CAP"),
            )
            final_qty = raw_qty
            
            # 3. Handle Precision & Min Quantity
            try:
                order_qty = float(self.exchange.amount_to_precision(self.symbol, final_qty))
                
                market = self.exchange.market(self.symbol)
                min_qty = market['limits']['amount']['min']
                
                if order_qty < min_qty:
                    logger.warning(f"⚠️ Qty {order_qty} < Min {min_qty}. Adjusting to min.")
                    order_qty = min_qty
            except Exception as e:
                logger.error(f"Precision calculation error: {e}")
                order_qty = round(final_qty, 3) # Fallback

            self.quantity = order_qty
            logger.info(
                f"Order Execution: side={'LONG' if direction==1 else 'SHORT'}, "
                f"risk_pct={risk_pct:.4f}, risk_qty={raw_qty:.4f}, final_qty={self.quantity}"
            )
            
            if not CONFIG["DRY_RUN"]:
                try:
                    # Set leverage before order
                    self.exchange.set_leverage(int(CONFIG.get("MAX_LEVERAGE", 5)), self.symbol)
                    
                    side = 'buy' if direction == 1 else 'sell'
                    order = self.exchange.create_market_order(self.symbol, side, self.quantity)
                    fill = self._resolve_market_fill(order, price, self.quantity)
                    self.quantity = fill["quantity"]
                    logger.info(f"✅ Opened Position: {side} {fill['quantity']} @ {fill['price']:,.2f}")
                    return fill
                except Exception as e:
                    logger.error(f"❌ Entry Order Failed: {e}")
                    self.notifier.notify_error(f"Order Failed: {e}")
                    return self._build_fill_result(False, price, 0.0)
            return self._build_fill_result(True, price, self.quantity)

if __name__ == "__main__":
    bot = TrendCrusherLive()
    bot.run()
