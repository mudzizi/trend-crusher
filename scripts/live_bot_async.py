import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import logging
import signal
import time
from datetime import datetime, timedelta
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx, calculate_choppiness, calculate_chaos_index, calculate_squeeze_score
from src.strategy import TrendCrusherV2
from src.telegram_utils import TelegramNotifier
from src.db_manager import DBManager
from src.websocket_manager import BinanceWebSocketManager
from src.portfolio_manager_async import PortfolioManagerAsync

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
        self.lock = asyncio.Lock() 
        
        self.settings = CONFIG.copy()
        if "SYMBOL_SETTINGS" in CONFIG and self.symbol in CONFIG["SYMBOL_SETTINGS"]:
            self.settings.update(CONFIG["SYMBOL_SETTINGS"][self.symbol])
        
        # Strategy Engine Instance (V7.1)
        self.engine = TrendCrusherV2(config=self.settings)
        
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.sl_order_id = None
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.is_halted = False 
        self.active_sniper_order_id = None 
        self.use_sniper = self.settings.get("USE_SNIPER", True) 
        self.active_retest_order_id = None 
        self.use_retest_maker = self.settings.get("USE_RETEST_MAKER", False) 
        self.retest_order_ts = None 
        self.is_processing_fill = False
        
        self.ohlcv_1h = None
        self.ohlcv_4h = None
        self.last_price = 0
        self.df_indicators = None
        
        # Throttling & Sync states
        self.last_db_record_ts = 0
        self.last_indicator_calc_ts = 0
        self.last_sl_sync_price = 0
        self.last_fill_poll_ts = 0
        self.entry_fee = 0

    def hot_reload_settings(self, new_params):
        self.settings.update(new_params)
        self.engine.c = self.settings
        self.logger.info(f"⚙️ Settings Hot-Reloaded: {new_params}")

    async def retry_api_call(self, func, *args, max_retries=3, delay=2, **kwargs):
        for i in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if i == max_retries - 1: raise e
                self.logger.warning(f"⚠️ API Error: {e}. Retrying {i+1}/{max_retries}...")
                await asyncio.sleep(delay * (i + 1))

    async def fetch_ohlcv(self, tf, limit=1000):
        ohlcv = await self.retry_api_call(self.exchange.fetch_ohlcv, self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def fetch_trigger_order(self, order_id):
        return await self.retry_api_call(self.exchange.fetch_order, order_id, self.symbol, params={'trigger': True})

    async def cancel_trigger_order(self, order_id):
        return await self.retry_api_call(self.exchange.cancel_order, order_id, self.symbol, params={'trigger': True})

    async def create_reduce_only_market_order(self, side, amount):
        return await self.retry_api_call(self.exchange.create_order, self.symbol, 'market', side, amount, None, params={'reduceOnly': True})

    async def _is_over_safety_limit(self, new_order_value_usdt=0):
        if self.settings.get("DRY_RUN"): return False
        limit = float(self.settings.get("MAX_POSITION_VALUE_USDT", 1000.0))
        try:
            positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
            pos = next((p for p in positions if p['symbol'] == self.symbol or p['symbol'].replace(':USDT','') == self.symbol), None)
            current_pos_value = abs(float(pos['notional'])) if pos and pos.get('notional') else 0
            open_orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
            pending_value = 0
            for o in open_orders:
                price = float(o.get('stopPrice') or o.get('price') or self.last_price)
                qty = float(o.get('amount', 0))
                pending_value += (price * qty)
            total_exposure = current_pos_value + pending_value + new_order_value_usdt
            if total_exposure > limit:
                self.logger.warning(f"⚠️ SAFETY LIMIT REACHED: Total exposure ${total_exposure:,.2f} exceeds limit ${limit:,.2f}.")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error in safety limit check: {e}")
            return True 

    async def initialize(self):
        try:
            state = self.db.get_bot_state(self.symbol)
            if state:
                self.position = int(state['position'])
                self.entry_price = float(state['entry_price'])
                self.quantity = float(state['quantity'])
                self.max_price_seen = float(state['max_price'])
                self.min_price_seen = float(state.get('min_price', float('inf')))
                self.sl_price = float(state.get('sl_price', 0))
                self.sl_order_id = state['sl_order_id']
                self.active_sniper_order_id = state.get('sniper_order_id')
                self.active_retest_order_id = state.get('retest_order_id')
                self.logger.info(f"💾 Recovered from DB: Pos={self.position}, Entry={self.entry_price}, Sniper={self.active_sniper_order_id}")

            self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"], limit=1000)
            self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"], limit=1000)
            self._update_indicators()
            asyncio.create_task(self._record_live_status())
            
            # [SSOT] Mandatory initial sync with exchange
            await self.sync_all_orders()
            self._initialized = True
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize {self.symbol}: {e}")
            raise e

    def _update_indicators(self, is_live=False):
        if self.ohlcv_1h is not None and self.ohlcv_4h is not None:
            self.df_indicators = self.engine.calculate_indicators(self.ohlcv_1h, self.ohlcv_4h, self.settings, is_live=is_live)
            if is_live:
                last = self.df_indicators.iloc[-1]
                self.logger.info(f"📊 Indicators: Price={self.last_price:.4f}, ADX={last['adx']:.1f}, Chaos={last['chaos']:.1f}, Squeeze={'YES' if last['squeeze']>0 else 'NO'}")

    async def on_kline_update(self, tf, kline):
        async with self.lock:
            try:
                signal_tf = self.settings["SIGNAL_TIMEFRAME"]
                if tf == signal_tf:
                    self.ohlcv_1h = await self.fetch_ohlcv(tf, limit=1000)
                    self._update_indicators(is_live=True)
                    if kline['x']:
                        last_row = self.df_indicators.iloc[-1]
                        self.db.log_history_1h(self.symbol, self.df_indicators.index[-1].strftime("%Y-%m-%d %H:%M:%S"),
                            float(last_row['close']), float(last_row['ema_h']), float(last_row['upper']), float(last_row['lower']),
                            float(last_row['volume']), float(last_row['adx']), float(last_row.get('chaos', 0)), float(last_row.get('squeeze', 0)),
                            float(last_row.get('ema_slope', 0)), float(last_row.get('chop', 0)))
                elif tf == self.settings["TREND_TIMEFRAME"]:
                    self.ohlcv_4h = await self.fetch_ohlcv(tf, limit=1000)
            except Exception as e: self.logger.error(f"Kline update error: {e}")

    async def on_mark_price_update(self, price):
        async with self.lock:
            self.last_price = price
            now = time.time()
            if now - self.last_db_record_ts > 5: await self._record_live_status(); self.last_db_record_ts = now
            if self.position != 0 or self.is_processing_fill: await self.check_exit()
            else: await self.check_entry()

    async def check_entry(self):
        if self.is_halted or self.df_indicators is None: return
        row = self.df_indicators.iloc[-1]
        is_ambushing = bool(self.active_sniper_order_id or self.active_retest_order_id)
        sig_type, target_p, sl_p = self.engine.check_entry_signal(row, self.last_price, self.use_sniper, self.use_retest_maker, self.settings, is_ambushing=is_ambushing)
        if sig_type is None:
            if self.active_sniper_order_id: await self.cancel_sniper_ambush()
            if self.active_retest_order_id: await self.cancel_retest_order()
            return
        if self.active_retest_order_id: return 
        direction = 1 if target_p > row['ema_h'] else -1
        if sig_type == 'RETEST': await self.manage_retest_ambush(direction, target_p, sl_p)
        elif sig_type == 'SNIPER': await self.manage_sniper_ambush(direction, target_p, row['atr'])
        elif sig_type == 'MARKET': await self.execute_entry(direction, row['atr'])

    async def check_exit(self):
        if self.df_indicators is None or self.position == 0: return
        if not self.sl_order_id and not self.settings["DRY_RUN"]:
            await self.sync_all_orders()
            if not self.sl_order_id and self.position != 0: await self.sync_sl_to_exchange(force_create=True)

        if self.position == 1: self.max_price_seen = max(self.max_price_seen, self.last_price)
        else: self.min_price_seen = min(self.min_price_seen, self.last_price)

        row = self.df_indicators.iloc[-1]
        state = {'position': self.position, 'entry_price': self.entry_price, 'max_price_seen': self.max_price_seen, 'min_price_seen': self.min_price_seen, 'sl_price': self.sl_price}
        old_sl = self.sl_price
        is_exit_triggered = self.engine.check_exit_signal(row, self.last_price, state, self.settings)
        self.sl_price = state['sl_price']

        sync_needed = False
        if self.last_sl_sync_price == 0: sync_needed = True
        elif abs(self.sl_price - self.last_sl_sync_price) / self.last_sl_sync_price > 0.0003: sync_needed = True

        if sync_needed and not is_exit_triggered:
            self.logger.info(f"🔄 SL Update Required: {old_sl:,.2f} -> {self.sl_price:,.2f}")
            await self.sync_sl_to_exchange()

        if is_exit_triggered:
            sync_diff = abs(self.sl_price - self.last_sl_sync_price) / (self.last_sl_sync_price or 1)
            if sync_diff > 0.0005:
                self.logger.warning(f"🚨 {self.symbol} SL Hit before Sync. Emergency Exit!")
                await self.execute_exit(); return
            if (self.position == 1 and self.last_price <= self.sl_price) or (self.position == -1 and self.last_price >= self.sl_price):
                return

    async def sync_all_orders(self):
        if self.settings["DRY_RUN"]: return
        try:
            positions = await self.retry_api_call(self.exchange.fetch_positions)
            pos = next((p for p in positions if p['symbol'] == self.symbol or p['symbol'].replace(':USDT','') == self.symbol), None)
            
            if pos and float(pos['contracts']) != 0:
                actual_qty, actual_entry = abs(float(pos['contracts'])), float(pos['entryPrice'])
                side_f = pos.get('side', '').lower()
                actual_side = -1 if side_f == 'short' or float(pos['contracts']) < 0 else 1
                
                if self.position != actual_side or abs(self.entry_price - actual_entry) > 0.1 or abs(self.quantity - actual_qty) > 0.0001:
                    self.logger.info(f"🔄 State Repaired for {self.symbol}: Pos {self.position}->{actual_side}")
                    self.position, self.entry_price, self.quantity = actual_side, actual_entry, actual_qty
                    self.max_price_seen = self.min_price_seen = actual_entry
                    self.persist_state()
                
                if self.sl_price == 0 and self.df_indicators is not None:
                    row = self.df_indicators.iloc[-1]
                    self.sl_price = self.entry_price - (row['atr'] * self.settings.get("INITIAL_SL_ATR", 2.0)) if self.position == 1 else self.entry_price + (row['atr'] * self.settings.get("INITIAL_SL_ATR", 2.0))
                    self.logger.info(f"🛡️ Initial SL Calculated: {self.sl_price:,.2f}")
            else:
                if positions and self.position != 0:
                    self.logger.warning(f"⚠️ Exchange says NO position. Resetting."); self.position = 0; self.persist_state()
                    await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol)

            # Adopt SL order from exchange
            if not self.sl_order_id and self.position != 0:
                open_orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
                target_side = 'sell' if self.position == 1 else 'buy'
                for o in open_orders:
                    if ('STOP' in str(o.get('type','')).upper() or 'TAKE_PROFIT' in str(o.get('type','')).upper()) and str(o.get('side','')).lower() == target_side:
                        self.sl_order_id, self.sl_price = o['id'], float(o.get('stopPrice') or o.get('price') or self.sl_price)
                        self.last_sl_sync_price = self.sl_price
                        self.logger.info(f"🛡️ SL Adopted: ID={self.sl_order_id}, Price={self.sl_price:,.2f}"); self.persist_state(); break
        except Exception as e: self.logger.error(f"Sync error: {e}")

    async def sync_sl_to_exchange(self, force_create=False):
        if self.settings["DRY_RUN"] or self.position == 0 or self.quantity <= 0: return
        if not self.sl_order_id and not force_create: return
        target_sl, target_qty, target_side = self.sl_price, self.quantity, ('sell' if self.position == 1 else 'buy')
        try:
            self.logger.info(f"🔄 Syncing SL for {self.symbol} -> {target_sl:,.2f}")
            await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol) # [NUCLEAR CLEANUP]
            params = {'stopPrice': target_sl, 'reduceOnly': True}
            sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', target_side, target_qty, None, params)
            old_sync_p = self.last_sl_sync_price
            self.sl_order_id, self.last_sl_sync_price = sl_order['id'], target_sl
            self.persist_state()
            if old_sync_p == 0 or abs(target_sl - old_sync_p) / old_sync_p > 0.001:
                self.notifier.send_message(f"🛡️ **SL Synchronized: {self.symbol}**\n- New SL: `{target_sl:,.2f}`\n- Mark Price: `{self.last_price:,.2f}`")
        except Exception as e: self.logger.error(f"❌ SL Sync Failed: {e}")

    async def execute_entry(self, direction, atr):
        side_str = "LONG" if direction == 1 else "SHORT"
        self.sl_price = float(self.last_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else self.last_price + (atr * self.settings["INITIAL_SL_ATR"]))
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if not qty or qty <= 0: return
        self.quantity = float(qty)
        if await self._is_over_safety_limit(self.quantity * self.last_price): return
        try:
            if not self.settings["DRY_RUN"]:
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, 'buy' if direction == 1 else 'sell', self.quantity)
                self.entry_price = float(order.get('average') or order.get('price') or self.last_price)
                self.quantity = float(order.get('filled') or self.quantity)
                await self.sync_sl_to_exchange(force_create=True)
            else: self.entry_price = self.last_price
            self.position = direction
            self.max_price_seen = self.min_price_seen = self.entry_price
            self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
            self.persist_state(); self.notifier.notify_entry(f"Async {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)
        except Exception as e: self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        if self.position == 0: return
        try:
            if not self.settings["DRY_RUN"]:
                try: await self.create_reduce_only_market_order('sell' if self.position == 1 else 'buy', self.quantity)
                except Exception as e:
                    if "-2022" in str(e): self.logger.warning(f"⚠️ ReduceOnly rejected. Resetting."); await self.sync_all_orders(); return
                    raise e
            self.logger.info(f"✅ Trade Closed: {self.symbol}"); self.position = 0; self.persist_state()
        except Exception as e: self.logger.error(f"Exit error: {e}")

    async def force_exit(self):
        self.logger.info(f"🚨 FORCE EXIT {self.symbol}")
        await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol)
        if self.position != 0: await self.execute_exit()

    def get_detailed_status(self):
        if self.df_indicators is None or self.df_indicators.empty: return f"• **{self.symbol}**: No data."
        row, pos_str = self.df_indicators.iloc[-1], "IDLE"
        if self.position == 1: pos_str = "🟢 LONG"
        elif self.position == -1: pos_str = "🔴 SHORT"
        pnl_pct = ((self.last_price / self.entry_price) - 1) * 100 * self.position if self.position != 0 and self.entry_price != 0 else 0
        return f"• **{self.symbol}**: {pos_str} ({pnl_pct:+.2f}%) | SL: {self.sl_price:,.2f}\n  - Prc: {self.last_price:,.2f} | Indicators: Vol {row['volume']/row['avg_vol']*100:.1f}% | Chaos {row.get('chaos',0):.1f}\n"

    def persist_state(self):
        try: self.db.save_bot_state(self.symbol, self.position, self.entry_price, self.quantity, self.max_price_seen, self.min_price_seen, self.sl_price, self.sl_order_id, self.active_sniper_order_id, self.active_retest_order_id)
        except Exception as e: self.logger.error(f"Persist error: {e}")

async def handle_commands(bots, notifier, pm):
    offset = None
    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset, msg = update["update_id"] + 1, update.get("message", {})
                    text = msg.get("text", "")
                    if text == "/status":
                        status_report = "📊 **Status Report**\n\n"
                        for sym, bot in bots.items(): status_report += bot.get_detailed_status()
                        notifier.send_message(status_report)
                    elif text == "/close_all":
                        await asyncio.gather(*[bot.force_exit() for bot in bots.values()])
                        notifier.send_message("✅ Closed all."); os._exit(0)
        except Exception as e: logger.error(f"Command error: {e}")
        await asyncio.sleep(2)

async def main():
    db, notifier = DBManager(), TelegramNotifier()
    exchange = getattr(ccxt, CONFIG["EXCHANGE"])({'apiKey': CONFIG["BINANCE_API_KEY"], 'secret': CONFIG["BINANCE_SECRET"], 'options': {'defaultType': 'future'}})
    pm = PortfolioManagerAsync(exchange, CONFIG)
    await exchange.load_markets()
    bots = {symbol: SymbolBotAsync(symbol, exchange, pm, notifier, db) for symbol in CONFIG["SYMBOLS_LIST"]}
    for bot in bots.values(): await bot.initialize()
    ws_manager = BinanceWebSocketManager(CONFIG["SYMBOLS_LIST"], api_key=CONFIG["BINANCE_API_KEY"], api_secret=CONFIG["BINANCE_SECRET"])
    async def ws_loop():
        async def process_msg(payload):
            e_type = payload.get('e')
            raw_symbol = payload.get('s') if 's' in payload else (payload['o']['s'] if 'o' in payload else None)
            if not raw_symbol: return
            symbol = raw_symbol if raw_symbol in bots else (raw_symbol.replace("USDT", "/USDT") if raw_symbol.replace("USDT", "/USDT") in bots else None)
            if symbol:
                bots[symbol].last_ws_msg_ts = time.time()
                if e_type == 'kline': await bots[symbol].on_kline_update(payload['k']['i'], payload['k'])
                elif e_type == 'markPriceUpdate': await bots[symbol].on_mark_price_update(float(payload['p']))
                elif e_type == 'ORDER_TRADE_UPDATE': await bots[symbol].on_order_update(payload['o'])
        async for msg in ws_manager.stream():
            if isinstance(msg, dict) and msg.get('e') == 'WS_RECONNECTED':
                for bot in bots.values(): asyncio.create_task(bot.sync_all_orders())
                continue
            asyncio.create_task(process_msg(msg.get('data', msg) if isinstance(msg, dict) else msg))
    logger.info(f"🚀 TrendCrusher {CONFIG['VERSION']} Started.")
    await asyncio.gather(ws_loop(), handle_commands(bots, notifier, pm))

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as fatal_e: print(f"Fatal: {fatal_e}")
