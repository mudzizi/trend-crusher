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
        
        self.last_db_record_ts = 0
        self.last_indicator_calc_ts = 0
        self.last_sl_sync_price = 0
        self.last_fill_poll_ts = 0
        self.entry_fee = 0
        self._initialized = False

    def hot_reload_settings(self, new_params):
        self.settings.update(new_params)
        self.engine.c = self.settings
        self.logger.info(f"⚙️ Settings Hot-Reloaded: {new_params}")

    async def retry_api_call(self, func, *args, max_retries=3, delay=2, **kwargs):
        for i in range(max_retries):
            try: return await func(*args, **kwargs)
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
            pos = next((p for p in positions if p['symbol'].replace('/', '').split(':')[0] == self.symbol.replace('/', '')), None)
            current_pos_value = abs(float(pos['notional'])) if pos and pos.get('notional') else 0
            open_orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
            pending_value = 0
            for o in open_orders:
                price = float(o.get('stopPrice') or o.get('price') or self.last_price)
                qty = float(o.get('amount', 0))
                pending_value += (price * qty)
            total_exposure = current_pos_value + pending_value + new_order_value_usdt
            if total_exposure > limit:
                self.logger.warning(f"⚠️ SAFETY LIMIT REACHED: ${total_exposure:,.2f} > ${limit:,.2f}")
                return True
            return False
        except Exception as e: self.logger.error(f"Safety check error: {e}"); return True 

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
            self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"], limit=1000)
            self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"], limit=1000)
            self._update_indicators()
            asyncio.create_task(self._record_live_status())
            await self.sync_all_orders()
            self._initialized = True
        except Exception as e: self.logger.error(f"❌ Init failed: {e}"); raise e

    def _update_indicators(self, is_live=False):
        if self.ohlcv_1h is not None and self.ohlcv_4h is not None:
            self.df_indicators = self.engine.calculate_indicators(self.ohlcv_1h, self.ohlcv_4h, self.settings, is_live=is_live)

    async def _record_live_status(self):
        if self.df_indicators is None or self.df_indicators.empty: return
        try:
            row = self.df_indicators.iloc[-1]
            v_t = row['avg_vol'] * self.settings.get('VOL_MULTIPLIER', 2.0)
            v_r = (row['volume'] / v_t * 100) if v_t > 0 else 0
            a_r = row['adx'] / self.settings.get('ADX_FILTER_LEVEL', 25.0) * 100
            ema, upper, lower = row['ema_h'], row['upper'], row['lower']
            dist = abs((upper if self.last_price > ema else lower) - self.last_price)
            prox = max(0, 1.0 - (dist / ((upper if self.last_price > ema else lower) * self.settings.get('SNIPER_PROXIMITY_PCT', 0.005)))) * 100
            pnl_pct = ((self.last_price / self.entry_price) - 1) * 100 * self.position if self.position != 0 and self.entry_price != 0 else 0
            # [FIXED] Correct method name from src/db_manager.py: update_live_status
            self.db.update_live_status(self.symbol, v_r, a_r, prox, True, 100, self.last_price, upper, lower, row['adx'], ema, row['chaos'], row['squeeze'], row['ema_slope'], row['chop'])
        except Exception as e: self.logger.error(f"DB log error: {e}")

    async def on_mark_price_update(self, price):
        async with self.lock:
            self.last_price = price
            now = time.time()
            if now - self.last_db_record_ts > 5: await self._record_live_status(); self.last_db_record_ts = now
            if now - self.last_fill_poll_ts > 30:
                if self.active_sniper_order_id: await self.check_sniper_fill()
                if self.active_retest_order_id: await self.check_retest_fill()
                self.last_fill_poll_ts = now
            if self.position != 0 or self.is_processing_fill: await self.check_exit()
            else: await self.check_entry()

    async def on_kline_update(self, tf, kline):
        async with self.lock:
            try:
                # 1. Update memory buffer instead of REST fetch for efficiency
                k_data = {
                    'timestamp': pd.to_datetime(kline['t'], unit='ms'),
                    'open': float(kline['o']), 'high': float(kline['h']),
                    'low': float(kline['l']), 'close': float(kline['c']),
                    'volume': float(kline['v'])
                }
                
                if tf == self.settings["SIGNAL_TIMEFRAME"]:
                    if self.ohlcv_1h is not None:
                        # Update last row or append new one
                        if k_data['timestamp'] == self.ohlcv_1h.iloc[-1]['timestamp']:
                            self.ohlcv_1h.iloc[-1] = k_data
                        else:
                            self.ohlcv_1h = pd.concat([self.ohlcv_1h, pd.DataFrame([k_data])]).tail(1000)
                    
                    self._update_indicators(is_live=True)
                    
                    # 2. Only fetch full history from REST when candle CLOSES to maintain precision
                    if kline['x']:
                        self.ohlcv_1h = await self.fetch_ohlcv(tf, limit=1000)
                        self._update_indicators(is_live=True)
                        r = self.df_indicators.iloc[-1]
                        self.db.log_history_1h(self.symbol, self.df_indicators.index[-1].strftime("%Y-%m-%d %H:%M:%S"), float(r['close']), float(r['ema_h']), float(r['upper']), float(r['lower']), float(r['volume']), float(r['adx']), float(r['chaos']), float(r['squeeze']), float(r['ema_slope']), float(r['chop']))
                
                elif tf == self.settings["TREND_TIMEFRAME"]:
                    if self.ohlcv_4h is not None:
                        if k_data['timestamp'] == self.ohlcv_4h.iloc[-1]['timestamp']:
                            self.ohlcv_4h.iloc[-1] = k_data
                        else:
                            self.ohlcv_4h = pd.concat([self.ohlcv_4h, pd.DataFrame([k_data])]).tail(1000)
                    if kline['x']:
                        self.ohlcv_4h = await self.fetch_ohlcv(tf, limit=1000)
            except Exception as e: self.logger.error(f"Kline update error: {e}")

    async def on_order_update(self, o):
        async with self.lock:
            try:
                oid, status, side, qty, avg_p = o['i'], o['X'], o['S'].lower(), float(o['z']), float(o.get('ap') or o.get('L') or 0)
                if status == 'FILLED':
                    if oid == self.sl_order_id or (self.position != 0 and side == ('sell' if self.position == 1 else 'buy')):
                        self.logger.info(f"🛡️ SL/Exit FILLED for {self.symbol}")
                        await self._on_fill_success(-1 if side == 'buy' else 1, is_exit=True, price=avg_p)
                    elif oid == self.active_sniper_order_id:
                        self.logger.info(f"🎯 Sniper FILLED for {self.symbol}")
                        self.active_sniper_order_id = None
                        await self._on_fill_success(1 if side == 'buy' else -1, price=avg_p)
                    elif oid == self.active_retest_order_id:
                        self.logger.info(f"🎣 Retest FILLED for {self.symbol}")
                        self.active_retest_order_id = None
                        await self._on_fill_success(1 if side == 'buy' else -1, price=avg_p)
            except Exception as e: self.logger.error(f"Order update error: {e}")

    async def _on_fill_success(self, direction, is_exit=False, price=0):
        if is_exit:
            pnl_pct = ((price / self.entry_price) - 1) * 100 * self.position if self.entry_price != 0 else 0
            pnl_usdt = (price - self.entry_price) * self.quantity * self.position if self.entry_price != 0 else 0
            self.db.log_trade_close(self.symbol, price, pnl_pct, pnl_usdt)
            await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
            self.notifier.notify_exit(f"Async {self.symbol}", price, pnl_pct, pnl_usdt)
            self.position, self.entry_price, self.quantity, self.sl_order_id = 0, 0, 0, None
        else:
            self.position, self.entry_price = direction, price
            self.max_price_seen = self.min_price_seen = price
            self.db.log_trade_open(self.symbol, ('LONG' if direction==1 else 'SHORT'), price, self.quantity, 100)
            self.notifier.notify_entry(f"Async {self.symbol}", price, self.sl_price, 100)
            await self.sync_sl_to_exchange(force_create=True)
        self.persist_state()

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
            self.logger.warning(f"⚠️ {self.symbol} in position but NO SL order ID found. Attempting to recover...")
            await self.sync_all_orders()
            if not self.sl_order_id and self.position != 0:
                self.logger.info(f"🛡️ Creating missing SL order for {self.symbol}...")
                await self.sync_sl_to_exchange(force_create=True)
                if not self.sl_order_id:
                    self.logger.warning(f"⚠️ Failed to create SL order for {self.symbol}. Will retry in next loop. Monitor manually!")
                    self.notifier.send_message(f"⚠️ **SL Creation Failed: {self.symbol}**\n봇이 다음 루프에서 재시도를 진행합니다. 확인이 필요합니다.")
                    return
        row = self.df_indicators.iloc[-1]
        if self.position == 1: self.max_price_seen = max(self.max_price_seen, self.last_price)
        else: self.min_price_seen = min(self.min_price_seen, self.last_price)
        state = {'position': self.position, 'entry_price': self.entry_price, 'max_price_seen': self.max_price_seen, 'min_price_seen': self.min_price_seen, 'sl_price': self.sl_price}
        triggered = self.engine.check_exit_signal(row, self.last_price, state, self.settings)
        self.sl_price = state['sl_price']
        if (self.last_sl_sync_price == 0 or abs(self.sl_price - self.last_sl_sync_price)/self.last_sl_sync_price > 0.0003) and not triggered:
            await self.sync_sl_to_exchange()
        if triggered:
            sync_diff = abs(self.sl_price - self.last_sl_sync_price)/(self.last_sl_sync_price or 1)
            if sync_diff > 0.0005: await self.execute_exit()

    async def manage_retest_ambush(self, direction, target_price, sl_price):
        if self.active_retest_order_id: return
        qty = await self.pm.calculate_order_qty(self.symbol, target_price, sl_price)
        if not qty or qty <= 0: return
        self.quantity = float(qty)
        if await self._is_over_safety_limit(self.quantity * target_price): return
        try:
            self.logger.info(f"🎣 Retest Maker: {target_price:,.2f}")
            order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'limit', 'buy' if direction==1 else 'sell', self.quantity, target_price, {'postOnly': True})
            self.active_retest_order_id, self.sl_price = order['id'], sl_price; self.persist_state()
        except Exception as e: self.logger.error(f"Retest error: {e}")

    async def manage_sniper_ambush(self, direction, target_price, atr):
        if self.active_sniper_order_id: return
        self.sl_price = target_price + (atr * self.settings["INITIAL_SL_ATR"]) * (-direction)
        qty = await self.pm.calculate_order_qty(self.symbol, target_price, self.sl_price)
        if not qty or qty <= 0: return
        self.quantity = float(qty)
        if await self._is_over_safety_limit(self.quantity * target_price): return
        try:
            self.logger.info(f"🏹 Sniper Stop: {target_price:,.2f}")
            order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'buy' if direction==1 else 'sell', self.quantity, None, {'stopPrice': target_price})
            self.active_sniper_order_id = order['id']; self.persist_state()
        except Exception as e: self.logger.error(f"Sniper error: {e}")

    async def cancel_retest_order(self):
        if not self.active_retest_order_id: return
        try: await self.retry_api_call(self.exchange.cancel_order, self.active_retest_order_id, self.symbol)
        except: pass
        finally: self.active_retest_order_id = None; self.persist_state()

    async def cancel_sniper_ambush(self):
        if not self.active_sniper_order_id: return
        try: await self.cancel_trigger_order(self.active_sniper_order_id)
        except: pass
        finally: self.active_sniper_order_id = None; self.persist_state()

    async def check_retest_fill(self):
        if not self.active_retest_order_id: return
        try:
            o = await self.retry_api_call(self.exchange.fetch_order, self.active_retest_order_id, self.symbol)
            if o['status'] == 'closed': await self.on_order_update({'i':o['id'], 'X':'FILLED', 'S':o['side'].upper(), 'z':o['filled'], 'ap':o['average']})
        except: pass

    async def check_sniper_fill(self):
        if not self.active_sniper_order_id: return
        try:
            o = await self.fetch_trigger_order(self.active_sniper_order_id)
            if o['status'] == 'closed': await self.on_order_update({'i':o['id'], 'X':'FILLED', 'S':o['side'].upper(), 'z':o['filled'], 'ap':o['average'] or o['price']})
        except: pass

    async def sync_all_orders(self):
        if self.settings["DRY_RUN"]: return
        try:
            positions = await self.retry_api_call(self.exchange.fetch_positions)
            pos = next((p for p in positions if p['symbol'].replace('/', '').split(':')[0] == self.symbol.replace('/', '')), None)
            if pos and float(pos['contracts']) != 0:
                self.position = -1 if pos.get('side','').lower()=='short' or float(pos['contracts'])<0 else 1
                self.entry_price, self.quantity = float(pos['entryPrice']), abs(float(pos['contracts']))
                if self.sl_price == 0 and self.df_indicators is not None:
                    row = self.df_indicators.iloc[-1]
                    self.sl_price = self.entry_price + (row['atr']*2.0)*(-self.position)
            else:
                if self.position != 0: self.position = 0; await self.exchange.cancel_all_orders(self.symbol)
            if not self.sl_order_id and self.position != 0:
                orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
                target_side = 'sell' if self.position == 1 else 'buy'
                for o in orders:
                    if ('STOP' in str(o.get('type','')).upper()) and o.get('side','').lower()==target_side:
                        self.sl_order_id, self.sl_price = o['id'], float(o.get('stopPrice', o.get('price', self.sl_price)))
                        self.last_sl_sync_price = self.sl_price; break
            if self.position == 0:
                orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
                for o in orders:
                    if 'STOP' in str(o.get('type', '')).upper() or o.get('stopPrice'):
                        self.active_sniper_order_id = o['id']
                        self.quantity = float(o.get('amount', self.quantity))
                    elif str(o.get('type', '')).upper() == 'LIMIT':
                        self.active_retest_order_id = o['id']
                        self.quantity = float(o.get('amount', self.quantity))
            self.persist_state()
        except Exception as e: self.logger.error(f"Sync error: {e}")

    async def sync_sl_to_exchange(self, force_create=False):
        if self.settings["DRY_RUN"]:
            self.sl_order_id = "DRY_SL"
            return
        if self.position == 0: return
        try:
            if self.sl_order_id:
                try:
                    await self.retry_api_call(self.exchange.cancel_order, self.sl_order_id, self.symbol)
                    self.logger.info(f"🛡️ Canceled old SL order by ID: {self.sl_order_id}")
                except Exception as ex:
                    pass
            orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
            target_side = 'sell' if self.position == 1 else 'buy'
            for o in orders:
                if ('STOP' in str(o.get('type','')).upper()) and o.get('side','').lower() == target_side:
                    try:
                        await self.retry_api_call(self.exchange.cancel_order, o['id'], self.symbol)
                        self.logger.info(f"🛡️ Canceled existing SL order: {o['id']}")
                    except Exception as ex:
                        self.logger.error(f"Error canceling SL order {o['id']}: {ex}")
            params = {'stopPrice': self.sl_price, 'reduceOnly': True}
            order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if self.position == 1 else 'buy', self.quantity, None, params)
            self.sl_order_id, self.last_sl_sync_price = order['id'], self.sl_price
            self.persist_state()
            self.notifier.send_message(f"🛡️ SL Sync: {self.symbol} -> {self.sl_price:,.2f}")
        except Exception as e: self.logger.error(f"SL Sync error: {e}")

    async def execute_entry(self, direction, atr):
        try:
            self.sl_price = self.last_price + (atr*2.0)*(-direction)
            qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
            if not qty or qty <= 0: return
            self.quantity = float(qty)
            if self.settings["DRY_RUN"]:
                self.entry_price = self.last_price
                await self._on_fill_success(direction, price=self.entry_price)
                return
            order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, 'buy' if direction == 1 else 'sell', self.quantity)
            self.entry_price = float(order.get('average', self.last_price)) if isinstance(order, dict) else self.last_price
            await self._on_fill_success(direction, price=self.entry_price)
        except Exception as e: self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        try:
            if self.settings["DRY_RUN"]:
                await self._on_fill_success(0, is_exit=True, price=self.last_price)
                return
            order = await self.create_reduce_only_market_order('sell' if self.position == 1 else 'buy', self.quantity)
            exit_price = float(order.get('average') or order.get('price') or self.last_price) if isinstance(order, dict) else self.last_price
            await self._on_fill_success(0, is_exit=True, price=exit_price)
        except Exception as e:
            if "-2022" in str(e): self.position = 0; self.persist_state(); await self.sync_all_orders(); return
            self.logger.error(f"Exit error: {e}")

    async def force_exit(self):
        await self.exchange.cancel_all_orders(self.symbol)
        if self.position != 0: await self.execute_exit()

    def persist_state(self):
        try: self.db.save_bot_state(self.symbol, self.position, self.entry_price, self.quantity, self.max_price_seen, self.min_price_seen, self.sl_price, self.sl_order_id, self.active_sniper_order_id, self.active_retest_order_id)
        except Exception as e: self.logger.error(f"Persist error: {e}")

    def get_detailed_status(self):
        if self.position != 0:
            pnl = ((self.last_price / self.entry_price) - 1) * 100 * self.position if self.entry_price != 0 else 0
            return f"• {self.symbol}: {'LONG' if self.position==1 else 'SHORT'} ({pnl:+.2f}%) | SL: {self.sl_price:,.2f}\n"
        elif self.active_sniper_order_id:
            return f"• {self.symbol}: SNIPER AMBUSH (OrderID: {self.active_sniper_order_id}) | SL: {self.sl_price:,.2f}\n"
        elif self.active_retest_order_id:
            return f"• {self.symbol}: RETEST AMBUSH (OrderID: {self.active_retest_order_id}) | SL: {self.sl_price:,.2f}\n"
        else:
            return f"• {self.symbol}: IDLE\n"

async def handle_commands(bots, notifier):
    offset = None
    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset, msg = update["update_id"] + 1, update.get("message", {})
                    text = msg.get("text", "")
                    if text == "/status":
                        status = "📊 Bot Status:\n"
                        for b in bots.values(): status += b.get_detailed_status()
                        notifier.send_message(status)
                    elif text == "/close_all":
                        await asyncio.gather(*[b.force_exit() for b in bots.values()])
                        notifier.send_message("✅ Closed all."); os._exit(0)
        except Exception as e: logger.error(f"Cmd error: {e}")
        await asyncio.sleep(2)

async def main():
    db, notifier = DBManager(), TelegramNotifier()
    exchange = getattr(ccxt, CONFIG["EXCHANGE"])({'apiKey': CONFIG["BINANCE_API_KEY"], 'secret': CONFIG["BINANCE_SECRET"], 'options': {'defaultType': 'future'}})
    pm = PortfolioManagerAsync(exchange, CONFIG)
    await exchange.load_markets()
    bots = {s: SymbolBotAsync(s, exchange, pm, notifier, db) for s in CONFIG["SYMBOLS_LIST"]}
    for b in bots.values(): await b.initialize()
    ws_manager = BinanceWebSocketManager(CONFIG["SYMBOLS_LIST"], api_key=CONFIG["BINANCE_API_KEY"], api_secret=CONFIG["BINANCE_SECRET"])
    async def ws_loop():
        async def process_msg(payload):
            e, raw_s = payload.get('e'), payload.get('s') if 's' in payload else (payload.get('o',{}).get('s'))
            if not raw_s: return
            s = raw_s if raw_s in bots else (raw_s.replace("USDT", "/USDT") if raw_s.replace("USDT", "/USDT") in bots else None)
            if s:
                if e == 'kline': await bots[s].on_kline_update(payload['k']['i'], payload['k'])
                elif e == 'markPriceUpdate': await bots[s].on_mark_price_update(float(payload['p']))
                elif e == 'ORDER_TRADE_UPDATE': await bots[s].on_order_update(payload['o'])
        async for msg in ws_manager.stream():
            if isinstance(msg, dict) and msg.get('e') == 'WS_RECONNECTED':
                for b in bots.values(): asyncio.create_task(b.sync_all_orders())
                continue
            asyncio.create_task(process_msg(msg.get('data', msg) if isinstance(msg, dict) else msg))
    logger.info(f"🚀 TrendCrusher {CONFIG['VERSION']} Started.")
    await asyncio.gather(ws_loop(), handle_commands(bots, notifier))

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as e: print(f"Fatal: {e}")
