import ccxt
import time
import pandas as pd
import os
import logging
from datetime import datetime
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.telegram_utils import TelegramNotifier
from src.db_manager import DBManager
from src.visualizer import TradingVisualizer
from src.portfolio_manager import PortfolioManager

# --- Logging Setup ---
os.makedirs("log", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler("log/live_bot_multi.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("MultiBot")

class SymbolBot:
    def __init__(self, symbol, exchange, portfolio_mgr, notifier, db, viz):
        self.symbol = symbol
        self.exchange = exchange
        self.pm = portfolio_mgr
        self.notifier = notifier
        self.db = db
        self.viz = viz
        self.logger = logging.getLogger(f"Bot-{symbol.split('/')[0]}")
        
        # Load symbol-specific settings, fallback to global CONFIG
        self.settings = CONFIG.copy()
        if "SYMBOL_SETTINGS" in CONFIG and self.symbol in CONFIG["SYMBOL_SETTINGS"]:
            self.settings.update(CONFIG["SYMBOL_SETTINGS"][self.symbol])
            self.logger.info(f"Loaded optimized settings for {self.symbol}")
        
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.sl_order_id = None
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        
        # Load initial state if exists (for restart safety)
        self.sync_state_from_db()
        
        # Smart Margin Setup (Only if no active position)
        self.check_and_set_isolated_margin()

    def check_and_set_isolated_margin(self):
        if self.settings.get("DRY_RUN", True): return
        
        try:
            # Check current position via exchange
            # Note: Using fetch_positions or similar depending on exchange
            positions = self.exchange.fetch_positions([self.symbol])
            size = 0
            if positions:
                size = abs(float(positions[0].get('contracts', 0)))
            
            if size == 0:
                self.logger.info(f"Setting margin mode to ISOLATED for {self.symbol}")
                try:
                    self.exchange.set_margin_mode('ISOLATED', self.symbol)
                except Exception as e:
                    if "No need to change margin mode" in str(e):
                        self.logger.info(f"Already in ISOLATED mode for {self.symbol}")
                    else:
                        self.logger.warning(f"Failed to set ISOLATED mode: {e}")
            else:
                self.logger.info(f"Skipping margin setup for {self.symbol} (Active position exists: {size})")
        except Exception as e:
            self.logger.error(f"Error during margin setup check: {e}")

    def sync_state_from_db(self):
        state = self.db.get_bot_state(self.symbol)
        if state:
            self.position = int(state['position'])
            self.entry_price = float(state['entry_price'])
            self.quantity = float(state['quantity'])
            self.max_price_seen = float(state['max_price'])
            self.min_price_seen = float(state['min_price'])
            self.sl_order_id = state['sl_order_id']
            self.logger.info(f"💾 Persistent state recovered: Pos={self.position}, Entry={self.entry_price}, MaxPrice={self.max_price_seen}")
        else:
            # Fallback to trades table for legacy support
            active_trades = self.db.get_active_trades()
            my_trade = active_trades[active_trades['symbol'] == self.symbol]
            if not my_trade.empty:
                row = my_trade.iloc[-1]
                self.position = 1 if row['side'] == 'LONG' else -1
                self.entry_price = float(row['open_price'])
                self.quantity = float(row['quantity'])
                self.max_price_seen = self.entry_price if self.position == 1 else 0
                self.min_price_seen = self.entry_price if self.position == -1 else float('inf')
                self.logger.info(f"Restored basic state from trades table: {row['side']} @ {self.entry_price}")

    def persist_state(self):
        try:
            self.db.save_bot_state(
                self.symbol, self.position, self.entry_price, self.quantity,
                self.max_price_seen, self.min_price_seen, self.sl_order_id
            )
        except Exception as e:
            self.logger.error(f"❌ Failed to persist state: {e}")

    def fetch_data(self, tf, limit=250):
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def retry_api_call(self, func, *args, max_retries=3, delay=2, **kwargs):
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if i == max_retries - 1: raise e
                self.logger.warning(f"⚠️ API Error: {e}. Retrying {i+1}/{max_retries}...")
                time.sleep(delay * (i + 1))

    def step(self):
        try:
            # 1. Fetch Indicators
            df_1h = self.retry_api_call(self.fetch_data, CONFIG["SIGNAL_TIMEFRAME"])
            df_4h = self.retry_api_call(self.fetch_data, CONFIG["TREND_TIMEFRAME"])
            
            # ...
            ticker = self.retry_api_call(self.exchange.fetch_ticker, self.symbol)
            c_close = float(ticker['last'])
            
            row = df_1h.iloc[-1]
            atr = row['atr']
            adx = row['adx']
            curr_vol = row['volume']
            avg_vol = row['avg_vol']
            
            # 2. Monitor Exit
            if self.position != 0:
                pnl_now = ((c_close / self.entry_price) - 1) * 100 * self.position
                
                # Adaptive SL logic
                curr_atr_mult = self.settings["TRAILING_ATR_MULT"]
                if self.settings.get("USE_ADAPTIVE_TRAIL", False):
                    for step_cfg in self.settings.get("ADAPTIVE_TRAIL_STEPS", []):
                        if pnl_now >= step_cfg['pnl_pct']:
                            curr_atr_mult = min(curr_atr_mult, step_cfg['atr_mult'])

                if self.position == 1:
                    self.max_price_seen = max(self.max_price_seen, c_close)
                    trail_sl = self.max_price_seen - (atr * curr_atr_mult)
                    active_sl = max(self.sl_price, trail_sl)
                else:
                    self.min_price_seen = min(self.min_price_seen, c_close)
                    trail_sl = self.min_price_seen + (atr * curr_atr_mult)
                    active_sl = min(self.sl_price, trail_sl)

                # --- Server-side SL Sync (V4 Safety) ---
                if not self.settings["DRY_RUN"] and self.sl_order_id and abs(active_sl - self.sl_price) > (self.entry_price * 0.001):
                    self.sync_sl_order(active_sl)
                    self.sl_price = active_sl

                should_exit = (self.position == 1 and c_close <= active_sl) or (self.position == -1 and c_close >= active_sl)
                
                if should_exit:
                    self.logger.info(f"🛑 EXIT SIGNAL: Closing at {c_close:,.2f}")
                    pnl_pct = ((c_close / self.entry_price) - 1) * 100 * self.position
                    gross_pnl_usdt = (self.entry_price * self.quantity) * (pnl_pct / 100)
                    fee_usdt = (self.entry_price * self.quantity * self.settings["FEE_RATE"]) + (c_close * self.quantity * self.settings["FEE_RATE"])
                    actual_pnl_usdt = gross_pnl_usdt - fee_usdt
                    
                    self.execute_market_order(0)
                    self.db.log_trade_close(self.symbol, c_close, pnl_pct, actual_pnl_usdt)
                    # Use symbol-specific balance update
                    self.pm.update_balance_after_trade(self.symbol, actual_pnl_usdt)
                    self.notifier.notify_exit(self.symbol, c_close, pnl_pct, actual_pnl_usdt)
                    
                    self.position = 0; self.sl_order_id = None
                    self.persist_state() # Clear state in DB
                    return 

            # 3. Monitor Entry
            if self.position == 0:
                is_vol_burst = curr_vol > (avg_vol * self.settings["VOL_MULTIPLIER"])
                is_trending = adx > self.settings["ADX_FILTER_LEVEL"]
                
                if is_vol_burst and is_trending and c_close > ema_4h_val and c_close > row['upper']:
                    self.logger.info(f"🚀 BUY SIGNAL: Price {c_close:,.2f} (ADX: {adx:.1f})")
                    self.sl_price = c_close - (atr * self.settings["INITIAL_SL_ATR"])
                    qty = self.pm.calculate_order_qty(self.symbol, c_close, self.sl_price)
                    if qty > 0:
                        self.quantity = self.sanitize_quantity(qty)
                        self.execute_market_order(1)
                        self.db.log_trade_open(self.symbol, "LONG", c_close, self.quantity, 100)
                        self.notifier.notify_entry(f"{self.symbol} LONG", c_close, self.sl_price, 100)
                        self.position = 1; self.entry_price = c_close; self.max_price_seen = c_close
                        self.persist_state() # Save entry state
                        
                elif is_vol_burst and is_trending and c_close < ema_4h_val and c_close < row['lower']:
                    self.logger.info(f"📉 SELL SIGNAL: Price {c_close:,.2f} (ADX: {adx:.1f})")
                    self.sl_price = c_close + (atr * self.settings["INITIAL_SL_ATR"])
                    qty = self.pm.calculate_order_qty(self.symbol, c_close, self.sl_price)
                    if qty > 0:
                        self.quantity = self.sanitize_quantity(qty)
                        self.execute_market_order(-1)
                        self.db.log_trade_open(self.symbol, "SHORT", c_close, self.quantity, 100)
                        self.notifier.notify_entry(f"{self.symbol} SHORT", c_close, self.sl_price, 100)
                        self.position = -1; self.entry_price = c_close; self.min_price_seen = c_close
                        self.persist_state() # Save entry state

            # Always persist at the end of a successful step if in position
            if self.position != 0:
                self.persist_state()

        except Exception as e:
            self.logger.error(f"Step Error: {e}")

    def sync_sl_order(self, new_sl):
        try:
            self.exchange.cancel_order(self.sl_order_id, self.symbol)
            sl_side = 'sell' if self.position == 1 else 'buy'
            params = {'stopPrice': new_sl, 'reduceOnly': True}
            sl_order = self.exchange.create_order(self.symbol, 'STOP_MARKET', sl_side, self.quantity, None, params)
            self.sl_order_id = sl_order['id']
            self.logger.info(f"🔄 Server-side SL Synced: {new_sl:,.2f}")
        except Exception as e:
            self.logger.error(f"Failed to sync SL: {e}")

    def sanitize_quantity(self, qty):
        try:
            market = self.exchange.market(self.symbol)
            qty_precision = float(self.exchange.amount_to_precision(self.symbol, qty))
            min_qty = market['limits']['amount']['min']
            return max(qty_precision, min_qty)
        except:
            return round(qty, 3)

    def execute_market_order(self, direction):
        if self.settings["DRY_RUN"]:
            self.logger.info(f"DRY RUN: Executing {'ENTRY' if direction!=0 else 'EXIT'} for {self.symbol}")
            return
        
        try:
            # Entry
            if direction != 0:
                side = 'buy' if direction == 1 else 'sell'
                self.exchange.set_leverage(int(self.settings.get("MAX_LEVERAGE", 5)), self.symbol)
                order = self.exchange.create_market_order(self.symbol, side, self.quantity)
                
                # Update with ACTUAL filled quantity from exchange
                if order and isinstance(order, dict):
                    actual_qty = float(order.get('filled', self.quantity))
                    if actual_qty > 0:
                        self.quantity = actual_qty
                    self.logger.info(f"✅ Market Order: {side} {self.quantity} (Actual: {actual_qty})")
                else:
                    self.logger.error(f"❌ Market order returned None or invalid response for {self.symbol}")
                    # Fallback to current quantity for notification/state consistency
                    self.logger.info(f"✅ Market Order (Assumption): {side} {self.quantity}")
                
                # Immediate Server-side SL (Always cover the actual filled qty)
                sl_side = 'sell' if direction == 1 else 'buy'
                params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                sl_order = self.exchange.create_order(self.symbol, 'STOP_MARKET', sl_side, self.quantity, None, params)
                self.sl_order_id = sl_order['id']
                self.logger.info(f"🛡️ Server-side SL Placed: {self.sl_price:,.2f} (ID: {self.sl_order_id})")
            
            # Exit
            else:
                if self.sl_order_id:
                    try: 
                        self.exchange.cancel_order(self.sl_order_id, self.symbol)
                        self.logger.info(f"🛡️ Cancelled Server SL (ID: {self.sl_order_id})")
                    except: 
                        pass
                    self.sl_order_id = None
                
                side = 'sell' if self.position == 1 else 'buy'
                self.exchange.create_market_order(self.symbol, side, self.quantity)
                self.logger.info(f"✅ Position Closed: {side} {self.quantity}")
                
        except Exception as e:
            self.logger.error(f"Order Execution Failed: {e}")
            raise e

def main():
    exchange = ccxt.binance({
        'apiKey': CONFIG["BINANCE_API_KEY"],
        'secret': CONFIG["BINANCE_SECRET"],
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    exchange.load_markets()
    
    db = DBManager()
    pm = PortfolioManager(exchange, CONFIG)
    notifier = TelegramNotifier()
    notifier.set_commands()
    viz = TradingVisualizer()
    
    symbols = CONFIG["SYMBOLS_LIST"]
    bots = [SymbolBot(sym, exchange, pm, notifier, db, viz) for sym in symbols]
    
    logger.info(f"Starting Multi-Symbol Bot {CONFIG['VERSION']} with {len(bots)} pairs...")
    notifier.notify_status(f"🚀 Multi-Symbol Bot {CONFIG['VERSION']} Started: {', '.join(symbols)}")
    
    # Initialize virtual balances for each symbol if needed
    if CONFIG["DRY_RUN"]:
        for sym in symbols:
            if db.get_equity_history(symbol=sym).empty:
                sym_seed = CONFIG["SYMBOL_SETTINGS"].get(sym, {}).get("ALLOCATED_SEED", 1000.0)
                db.log_equity(sym_seed, symbol=sym)
                logger.info(f"Initialized virtual balance for {sym}: {sym_seed} USDT")

    while True:
        start_time = time.time()
        for bot in bots:
            bot.step()
            time.sleep(1) # Small delay between symbols to avoid burst rate limits
            
        elapsed = time.time() - start_time
        wait_time = max(0, CONFIG["LOOP_INTERVAL"] - elapsed)
        time.sleep(wait_time)

if __name__ == "__main__":
    main()
