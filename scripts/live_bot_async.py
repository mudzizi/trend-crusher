import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import logging
from datetime import datetime
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.telegram_utils import TelegramNotifier
from src.db_manager import DBManager
from src.visualizer import TradingVisualizer
from src.portfolio_manager_async import PortfolioManagerAsync
from src.websocket_manager import BinanceWebSocketManager

# --- Logging Setup ---
os.makedirs("log", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler("log/live_bot_async.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AsyncBot")

class SymbolBotAsync:
    def __init__(self, symbol, exchange, pm, notifier, db):
        self.symbol = symbol
        self.exchange = exchange
        self.pm = pm
        self.notifier = notifier
        self.db = db
        self.logger = logging.getLogger(f"Async-{symbol.split('/')[0]}")
        
        self.settings = CONFIG.copy()
        if "SYMBOL_SETTINGS" in CONFIG and self.symbol in CONFIG["SYMBOL_SETTINGS"]:
            self.settings.update(CONFIG["SYMBOL_SETTINGS"][self.symbol])
        
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.sl_order_id = None
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        
        # Internal state for incremental indicators
        self.ohlcv_1h = None
        self.ohlcv_4h = None
        self.last_price = 0

    async def initialize(self):
        """Initial sync from DB and REST API."""
        # 1. State recovery
        state = self.db.get_bot_state(self.symbol)
        if state:
            self.position = int(state['position'])
            self.entry_price = float(state['entry_price'])
            self.quantity = float(state['quantity'])
            self.max_price_seen = float(state['max_price'])
            self.sl_order_id = state['sl_order_id']
            self.logger.info(f"💾 Recovered: Pos={self.position}, Entry={self.entry_price}")

        # 2. Initial OHLCV fetch via REST
        self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"])
        self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"])
        self.logger.info(f"📊 Indicators Initialized")

    async def fetch_ohlcv(self, tf, limit=100):
        ohlcv = await self.exchange.fetch_ohlcv(self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def on_mark_price_update(self, price):
        """Triggered by WebSocket Mark Price stream."""
        self.last_price = price
        if self.position != 0:
            await self.check_exit()
        else:
            await self.check_entry()

    async def on_kline_update(self, tf, kline):
        """Update local OHLCV buffer when a candle closes or updates."""
        # For simplicity in this v7 prototype, we update indicators on candle close events
        if kline['x']: # Candle is closed
            self.logger.info(f"🕯️ Candle Closed ({tf}): Updating indicators...")
            if tf == self.settings["SIGNAL_TIMEFRAME"]:
                self.ohlcv_1h = await self.fetch_ohlcv(tf)
            else:
                self.ohlcv_4h = await self.fetch_ohlcv(tf)

    async def check_entry(self):
        if self.ohlcv_1h is None or self.ohlcv_4h is None: return
        
        # Calculate indicators on the fly
        df_1h = self.ohlcv_1h.copy()
        df_4h = self.ohlcv_4h.copy()
        
        upper, lower = calculate_donchian(df_1h, self.settings["DONCHIAN_PERIOD"])
        atr = calculate_atr(df_1h, self.settings["ATR_PERIOD"]).iloc[-1]
        avg_vol = calculate_avg_vol(df_1h, self.settings["AVG_VOL_PERIOD"]).iloc[-1]
        adx = calculate_adx(df_1h, 14).iloc[-1]
        ema_4h = calculate_ema(df_4h, self.settings["EMA_TREND_PERIOD"]).iloc[-1]
        
        curr_vol = df_1h.iloc[-1]['volume']
        
        is_vol_burst = curr_vol > (avg_vol * self.settings["VOL_MULTIPLIER"])
        is_trending = adx > self.settings["ADX_FILTER_LEVEL"]
        
        if is_vol_burst and is_trending and self.last_price > ema_4h:
            if self.last_price > upper.iloc[-1]:
                await self.execute_entry(1, atr)
            elif self.last_price < lower.iloc[-1]:
                await self.execute_entry(-1, atr)

    async def check_exit(self):
        pnl_now = ((self.last_price / self.entry_price) - 1) * 100 * self.position
        
        # Simplified Trailing Logic for Async
        atr = calculate_atr(self.ohlcv_1h, self.settings["ATR_PERIOD"]).iloc[-1]
        curr_atr_mult = self.settings["TRAILING_ATR_MULT"]
        
        # Adaptive adjustment
        if self.settings.get("USE_ADAPTIVE_TRAIL", False):
            for step in self.settings.get("ADAPTIVE_TRAIL_STEPS", []):
                if pnl_now >= step['pnl_pct']:
                    curr_atr_mult = min(curr_atr_mult, step['atr_mult'])

        if self.position == 1:
            self.max_price_seen = max(self.max_price_seen, self.last_price)
            active_sl = self.max_price_seen - (atr * curr_atr_mult)
            if self.last_price <= active_sl:
                await self.execute_exit()
        else:
            self.min_price_seen = min(self.min_price_seen, self.last_price)
            active_sl = self.min_price_seen + (atr * curr_atr_mult)
            if self.last_price >= active_sl:
                await self.execute_exit()

    async def execute_entry(self, direction, atr):
        side_str = "LONG" if direction == 1 else "SHORT"
        self.sl_price = self.last_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else self.last_price + (atr * self.settings["INITIAL_SL_ATR"])
        
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if qty <= 0: return

        self.quantity = qty
        try:
            if not self.settings["DRY_RUN"]:
                side = 'buy' if direction == 1 else 'sell'
                # 1. Market Entry Order with Retry
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, self.quantity)
                self.quantity = float(order.get('filled', self.quantity))
                
                # 2. Immediate Server-side SL (Critical Path)
                try:
                    params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                    sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
                    self.sl_order_id = sl_order['id']
                except Exception as sl_err:
                    # CRITICAL: Entry succeeded but SL failed. Liquidate immediately to stay safe!
                    self.logger.error(f"🚨 CRITICAL: SL placement failed after retries: {sl_err}. EMERGENCY LIQUIDATION!")
                    await self.exchange.create_market_order(self.symbol, 'sell' if direction == 1 else 'buy', self.quantity)
                    self.notifier.notify_error(f"EMERGENCY: SL failed for {self.symbol}. Position closed for safety.")
                    return

            self.position = direction
            self.entry_price = self.last_price
            self.max_price_seen = self.last_price
            self.min_price_seen = self.last_price
            self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
            self.persist_state()
            self.notifier.notify_entry(f"Async {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)

        except ccxt.InsufficientFunds as e:
            self.logger.error(f"❌ Insufficient Funds for {self.symbol}: {e}")
            self.notifier.notify_error(f"Budget Error: Insufficient funds to open {self.symbol}.")
        except ccxt.NetworkError as e:
            self.logger.error(f"🌐 Network Error during entry for {self.symbol}: {e}")
        except Exception as e:
            self.logger.error(f"🔥 Unexpected Entry Error for {self.symbol}: {e}")
            self.notifier.notify_error(f"Unexpected Entry Error ({self.symbol}): {str(e)[:100]}")

    async def execute_exit(self):
        pnl_pct = ((self.last_price / self.entry_price) - 1) * 100 * self.position
        try:
            if not self.settings["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                # 1. Market Exit Order with Retry
                await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, self.quantity)
                
                # 2. Cancel Pending SL
                if self.sl_order_id:
                    try: 
                        await self.retry_api_call(self.exchange.cancel_order, self.sl_order_id, self.symbol)
                    except ccxt.OrderNotFound:
                        pass # Already triggered or cancelled
                    except Exception as e:
                        self.logger.warning(f"Cleanup: Failed to cancel SL order {self.sl_order_id}: {e}")

            self.db.log_trade_close(self.symbol, self.last_price, pnl_pct, 0)
            await self.pm.update_balance_after_trade(self.symbol, 0)
            self.position = 0; self.sl_order_id = None
            self.persist_state()
            self.notifier.notify_exit(f"Async {self.symbol}", self.last_price, pnl_pct, 0)

        except ccxt.NetworkError as e:
            self.logger.error(f"🌐 Network Error during exit for {self.symbol}: {e}. Retrying in next tick...")
        except Exception as e:
            self.logger.error(f"🔥 Critical Exit Error for {self.symbol}: {e}")
            self.notifier.notify_error(f"CRITICAL EXIT ERROR ({self.symbol}): {str(e)[:100]}. Manual intervention required!")

    def persist_state(self):
        self.db.save_bot_state(self.symbol, self.position, self.entry_price, self.quantity, self.max_price_seen, self.min_price_seen, self.sl_order_id)

async def main():
    exchange = ccxt.binance({
        'apiKey': CONFIG["BINANCE_API_KEY"],
        'secret': CONFIG["BINANCE_SECRET"],
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    
    db = DBManager()
    pm = PortfolioManagerAsync(exchange, CONFIG)
    notifier = TelegramNotifier()
    
    symbols = CONFIG["SYMBOLS_LIST"]
    bots = {s.replace('/', '').lower(): SymbolBotAsync(s, exchange, pm, notifier, db) for s in symbols}
    
    for bot in bots.values():
        await bot.initialize()

    ws_manager = BinanceWebSocketManager(symbols)
    asyncio.create_task(ws_manager.connect())
    
    logger.info(f"🚀 v7.0.0-async Engine Started. Monitoring {len(symbols)} symbols...")

    while True:
        msg = await ws_manager.get_next_message()
        stream = msg.get('e')
        symbol_key = msg.get('s', '').lower()
        
        if symbol_key in bots:
            bot = bots[symbol_key]
            if stream == 'markPriceUpdate':
                await bot.on_mark_price_update(float(msg['p']))
            elif stream == 'kline':
                tf_map = {'1h': CONFIG['SIGNAL_TIMEFRAME'], '1m': '1m'} # Simplified map
                await bot.on_kline_update(msg['k']['i'], msg['k'])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
