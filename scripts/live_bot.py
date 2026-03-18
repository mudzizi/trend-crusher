import ccxt
import time
import pandas as pd
import os
import logging
from datetime import datetime
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.risk import calculate_position_size as shared_calculate_position_size
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
        
        self.db.log_equity(self.session_capital)
        
        logger.info("="*50)
        logger.info(f"🚀 TrendCrusher Live Bot Started")
        logger.info(f"Mode: {'DRY RUN' if CONFIG['DRY_RUN'] else 'LIVE'}")
        logger.info(f"Symbol: {self.symbol} | Seed: {self.initial_seed} USDT")
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

    def run(self):
        while True:
            try:
                df_1h, ema_4h_val = self.calculate_indicators()
                row = df_1h.iloc[-1]
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
                        pnl_pct = ((c_close / self.entry_price) - 1) * 100 * self.position
                        gross_pnl_usdt = (self.entry_price * self.quantity) * (pnl_pct / 100)
                        fee_usdt = (self.entry_price * self.quantity * CONFIG["FEE_RATE"]) + (c_close * self.quantity * CONFIG["FEE_RATE"])
                        actual_pnl_usdt = gross_pnl_usdt - fee_usdt
                        
                        logger.info(f"🛑 EXIT SIGNAL: Closing at {c_close:,.2f} | PnL: {actual_pnl_usdt:+.2f} USDT")
                        self.execute_order(0, c_close)
                        self.session_capital += actual_pnl_usdt
                        self.db.log_trade_close(c_close, pnl_pct, actual_pnl_usdt)
                        self.db.log_equity(self.session_capital)
                        
                        self.viz.generate_report(df_1h, self.db.get_trade_history(), self.db.get_equity_history(), self.symbol)
                        self.notifier.notify_exit("AUTO_EXIT", c_close, pnl_pct, actual_pnl_usdt)
                        self.position = 0

                # --- MONITORING ENTRY ---
                if self.position == 0:
                    is_vol_burst = curr_vol > (avg_vol * CONFIG["VOL_MULTIPLIER"])
                    
                    if is_vol_burst and c_close > ema_4h_val and c_close > upper:
                        logger.info(f"🚀 BUY SIGNAL: Price {c_close:,.2f} > Upper {upper:,.2f}")
                        self.sl_price = c_close - (atr * CONFIG["INITIAL_SL_ATR"])
                        self.execute_order(1, c_close)
                        vol_ratio = curr_vol / (avg_vol + 1e-10)
                        strength = min(100, vol_ratio * 50)
                        self.db.log_trade_open(self.symbol, "LONG", c_close, self.quantity, strength)
                        self.notifier.notify_entry("LONG", c_close, self.sl_price, strength)
                        self.position = 1; self.entry_price = c_close; self.max_price_seen = c_close
                        
                    elif is_vol_burst and c_close < ema_4h_val and c_close < lower:
                        logger.info(f"📉 SELL SIGNAL: Price {c_close:,.2f} < Lower {lower:,.2f}")
                        self.sl_price = c_close + (atr * CONFIG["INITIAL_SL_ATR"])
                        self.execute_order(-1, c_close)
                        strength = min(100, vol_ratio * 50)
                        self.db.log_trade_open(self.symbol, "SHORT", c_close, self.quantity, strength)
                        self.notifier.notify_entry("SHORT", c_close, self.sl_price, strength)
                        self.position = -1; self.entry_price = c_close; self.min_price_seen = c_close

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                self.notifier.notify_error(str(e))
            
            time.sleep(CONFIG["LOOP_INTERVAL"])

    def execute_order(self, direction, price):
        if direction == 0:
            if not CONFIG["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                try:
                    self.exchange.create_market_order(self.symbol, side, self.quantity)
                    logger.info(f"✅ Closed Position: {side} {self.quantity}")
                except Exception as e:
                    logger.error(f"❌ Exit Order Failed: {e}")
        else:
            # 1. Calculate Risk-based Quantity
            stop_dist = abs(price - self.sl_price)
            if stop_dist == 0: return

            raw_qty = shared_calculate_position_size(
                capital=self.session_capital,
                price=price,
                stop_loss_price=self.sl_price,
                risk_pct=CONFIG["RISK_PER_TRADE"],
                max_leverage=CONFIG.get("MAX_LEVERAGE"),
                max_trade_loss_pct_cap=CONFIG.get("MAX_TRADE_LOSS_PCT_CAP"),
            )
            final_qty = raw_qty
            
            # 3. Handle Precision & Min Quantity
            try:
                self.quantity = float(self.exchange.amount_to_precision(self.symbol, final_qty))
                
                market = self.exchange.market(self.symbol)
                min_qty = market['limits']['amount']['min']
                
                if self.quantity < min_qty:
                    logger.warning(f"⚠️ Qty {self.quantity} < Min {min_qty}. Adjusting to min.")
                    self.quantity = min_qty
            except Exception as e:
                logger.error(f"Precision calculation error: {e}")
                self.quantity = round(final_qty, 3) # Fallback

            logger.info(f"Order Execution: side={'LONG' if direction==1 else 'SHORT'}, risk_qty={raw_qty:.4f}, final_qty={self.quantity}")
            
            if not CONFIG["DRY_RUN"]:
                try:
                    # Set leverage before order
                    self.exchange.set_leverage(int(CONFIG.get("MAX_LEVERAGE", 5)), self.symbol)
                    
                    side = 'buy' if direction == 1 else 'sell'
                    self.exchange.create_market_order(self.symbol, side, self.quantity)
                    logger.info(f"✅ Opened Position: {side} {self.quantity}")
                except Exception as e:
                    logger.error(f"❌ Entry Order Failed: {e}")
                    self.notifier.notify_error(f"Order Failed: {e}")

if __name__ == "__main__":
    bot = TrendCrusherLive()
    bot.run()
