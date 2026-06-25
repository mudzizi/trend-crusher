import asyncio
import ccxt.async_support as ccxt
import pandas as pd

async def _maybe_await(coro_or_val):
    if asyncio.iscoroutine(coro_or_val) or hasattr(coro_or_val, '__await__'):
        return await coro_or_val
    return coro_or_val

import os
import logging
import signal
import time
from datetime import datetime, timedelta
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx, calculate_choppiness, calculate_chaos_index, calculate_squeeze_score
from src.strategy import TrendCrusherV2
from src.telegram_utils import TelegramNotifier
from src.async_db_manager import AsyncDBManager
from src.websocket_manager import BinanceWebSocketManager
from src.portfolio_manager_async import PortfolioManagerAsync
from src.bot.exchange_adapter import ExchangeAdapter
from src.bot.risk_manager import RiskManager


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
    def __init__(self, symbol, exchange, pm, notifier, db, exchange_adapter=None, risk_manager=None):
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

        dry_run = self.settings.get("DRY_RUN", False)
        # Auto-detect unit test mock environment
        if exchange and ('Mock' in exchange.__class__.__name__ or 'mock' in str(type(exchange)).lower()):
            dry_run = True
            self.settings["DRY_RUN"] = True
            
        self.adapter = exchange_adapter or ExchangeAdapter(exchange, symbol, dry_run=dry_run)
        self.risk_manager = risk_manager or RiskManager(dry_run=dry_run)

    def hot_reload_settings(self, new_params):
        self.settings.update(new_params)
        self.engine.c = self.settings
        self.logger.info(f"⚙️ Settings Hot-Reloaded: {new_params}")
        self.adapter.dry_run = self.settings.get("DRY_RUN", False)
        self.risk_manager.dry_run = self.settings.get("DRY_RUN", False)

    async def fetch_ohlcv(self, tf, limit=1000):
        return await self.adapter.fetch_ohlcv(tf, limit)

    async def fetch_trigger_order(self, order_id):
        return await self.adapter.fetch_trigger_order(order_id)

    async def cancel_trigger_order(self, order_id):
        return await self.adapter.cancel_trigger_order(order_id)

    async def create_reduce_only_market_order(self, side, amount):
        return await self.adapter.create_reduce_only_market_order(side, amount)

    async def get_all_open_orders(self):
        return await self.adapter.get_all_open_orders()

    async def _is_over_safety_limit(self, new_order_value_usdt=0):
        if self.settings.get("DRY_RUN"):
            return False
        return not await self.risk_manager.check_exposure_safety(
            self.symbol, self.last_price, new_order_value_usdt, self.adapter,
            self.settings.get("MAX_POSITION_VALUE_USDT", 1000.0)
        )
 

    async def initialize(self):
        try:
            state = await _maybe_await(self.db.get_bot_state(self.symbol))
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
            await self._backfill_history_1h()
            asyncio.create_task(self._record_live_status())
            await self.sync_all_orders()
            self._initialized = True
        except Exception as e: self.logger.error(f"❌ Init failed: {e}"); raise e

    def _update_indicators(self, is_live=False):
        if self.ohlcv_1h is not None and self.ohlcv_4h is not None:
            self.df_indicators = self.engine.calculate_indicators(self.ohlcv_1h, self.ohlcv_4h, self.settings, is_live=is_live)

    async def _backfill_history_1h(self):
        """Backfill and update last 120h of indicator data to history_1h table."""
        if self.df_indicators is None or self.df_indicators.empty:
            return
        try:
            df = self.df_indicators
            backfill_rows = df.tail(120)
            records = []
            for ts, r in backfill_rows.iterrows():
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, 'strftime') else str(ts)
                records.append({
                    'timestamp': ts_str,
                    'close': float(r['close']),
                    'ema': float(r['ema_h']),
                    'd_upper': float(r['upper']),
                    'd_lower': float(r['lower']),
                    'volume': float(r['volume']),
                    'adx': float(r['adx']),
                    'chaos': float(r.get('chaos', 0)),
                    'squeeze': float(r.get('squeeze', 0)),
                    'slope': float(r.get('ema_slope', 0)),
                    'chop': float(r.get('chop', 0)),
                    'adx_4h': float(r.get('adx_4h', 0))
                })
            await _maybe_await(self.db.log_history_1h_batch(self.symbol, records))
            self.logger.info(f"📊 [{self.symbol}] Backfilled/Updated {len(records)} history_1h records via batch insertion.")
        except Exception as e:
            self.logger.error(f"Backfill error for {self.symbol}: {e}")

    def _compute_signal_score(self, row):
        """Compute a dynamic 0-100 signal score based on entry readiness conditions."""
        c = self.settings
        checks = 0
        total = 6
        chaos_threshold = c.get('CHAOS_THRESHOLD', 20.0)
        adx_threshold = c.get('ADX_FILTER_LEVEL', 20.0)
        adx_4h_threshold = c.get('ADX_4H_THRESHOLD', 15.0)
        vol_mult = c.get('VOL_MULTIPLIER', 2.0)
        
        is_ambushing = bool(self.active_sniper_order_id or self.active_retest_order_id)
        
        cur_price = self.last_price if self.last_price > 0 else row['close']
        is_long = cur_price > row['ema_h']
        slope = row.get('ema_slope', 0)

        # Parameter Normalization (Hysteresis)
        v_target = vol_mult * 0.8 if is_ambushing else vol_mult
        a_target = adx_threshold * 0.8 if is_ambushing else adx_threshold
        a4_target = adx_4h_threshold * 0.8 if is_ambushing else adx_4h_threshold

        # Dynamic Barrier (applied if chaos_threshold > 0)
        v_mult_final = v_target
        a_target_final = a_target
        a4_target_final = a4_target
        
        chop = row.get('chop', 50.0)
        squeeze = row.get('squeeze', 0.0)
        
        if chaos_threshold > 0:
            # Choppiness Scaling
            if chop > 61.8:
                v_mult_final *= 1.8
            elif chop < 38.2:
                v_mult_final *= 0.8
            # Squeeze scaling
            if squeeze > 0:
                v_mult_final *= 0.7
            # Short position bias
            if not is_long:
                v_mult_final *= 0.6
                a_target_final *= 0.7
                a4_target_final *= 0.7

        # 1. Chaos gate
        if chaos_threshold > 0 and row.get('chaos', 0) >= chaos_threshold:
            checks += 1
        elif chaos_threshold <= 0:
            checks += 1
        # 2. Slope alignment
        if (is_long and slope > 0) or (not is_long and slope < 0):
            checks += 1
        # 3. Choppiness
        if chop < 61.8:
            checks += 1
        # 4. ADX 1H
        if row['adx'] >= a_target_final:
            checks += 1
        # 5. ADX 4H
        if row.get('adx_4h', 0) >= a4_target_final:
            checks += 1
        # 6. Volume
        if row['volume'] >= (row['avg_vol'] * v_mult_final):
            checks += 1
        # Squeeze bonus (adds up to ~14 points)
        if squeeze > 0:
            checks += 1
            total += 1
        return round(checks / total * 100, 1)

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
            score = self._compute_signal_score(row)
            await _maybe_await(self.db.update_live_status(self.symbol, v_r, a_r, prox, True, score, self.last_price, upper, lower, row['adx'], ema, row['chaos'], row['squeeze'], row['ema_slope'], row['chop'], row.get('adx_4h', 0)))
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
                k_data = {
                    'timestamp': pd.to_datetime(kline['t'], unit='ms'),
                    'open': float(kline['o']), 'high': float(kline['h']),
                    'low': float(kline['l']), 'close': float(kline['c']),
                    'volume': float(kline['v'])
                }
                
                if tf == self.settings["SIGNAL_TIMEFRAME"]:
                    if self.ohlcv_1h is not None:
                        if k_data['timestamp'] == self.ohlcv_1h.iloc[-1]['timestamp']:
                            self.ohlcv_1h.iloc[-1] = k_data
                        else:
                            self.ohlcv_1h = pd.concat([self.ohlcv_1h, pd.DataFrame([k_data])]).tail(1000)
                    
                    self._update_indicators(is_live=True)
                    
                    if kline['x']:
                        self.ohlcv_1h = await self.fetch_ohlcv(tf, limit=1000)
                        self._update_indicators(is_live=True)
                        closed_ts = pd.to_datetime(kline['t'], unit='ms')
                        if closed_ts in self.df_indicators.index:
                            r = self.df_indicators.loc[closed_ts]
                            await _maybe_await(self.db.log_history_1h(
                                self.symbol, 
                                closed_ts.strftime("%Y-%m-%d %H:%M:%S"), 
                                float(r['close']), float(r['ema_h']), float(r['upper']), float(r['lower']), 
                                float(r['volume']), float(r['adx']), float(r['chaos']), float(r['squeeze']), 
                                float(r['ema_slope']), float(r['chop']), float(r.get('adx_4h', 0))
                            ))
                        else:
                            r = self.df_indicators.iloc[-2] if len(self.df_indicators) > 1 else self.df_indicators.iloc[-1]
                            ts_val = self.df_indicators.index[-2] if len(self.df_indicators) > 1 else self.df_indicators.index[-1]
                            await _maybe_await(self.db.log_history_1h(
                                self.symbol, 
                                ts_val.strftime("%Y-%m-%d %H:%M:%S"), 
                                float(r['close']), float(r['ema_h']), float(r['upper']), float(r['lower']), 
                                float(r['volume']), float(r['adx']), float(r['chaos']), float(r['squeeze']), 
                                float(r['ema_slope']), float(r['chop']), float(r.get('adx_4h', 0))
                            ))
                
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
            if self.sl_order_id and not self.settings.get("DRY_RUN"):
                try:
                    await self.adapter.cancel_trigger_order(self.sl_order_id)
                    self.logger.info(f"🛡️ [{self.symbol}] Canceled SL order {self.sl_order_id} on position exit.")
                except Exception as ex:
                    self.logger.info(f"ℹ️ [{self.symbol}] SL order cancel request skipped/failed on exit (likely already filled/closed): {ex}")
            pnl_pct = ((price / self.entry_price) - 1) * 100 * self.position if self.entry_price != 0 else 0
            pnl_usdt = (price - self.entry_price) * self.quantity * self.position if self.entry_price != 0 else 0
            await _maybe_await(self.db.log_trade_close(self.symbol, price, pnl_pct, pnl_usdt))
            await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
            self.notifier.notify_exit(f"Async {self.symbol}", price, pnl_pct, pnl_usdt)
            self.position, self.entry_price, self.quantity, self.sl_order_id = 0, 0, 0, None
        else:
            self.position, self.entry_price = direction, price
            self.max_price_seen = self.min_price_seen = price
            await _maybe_await(self.db.log_trade_open(self.symbol, ('LONG' if direction==1 else 'SHORT'), price, self.quantity, 100))
            self.notifier.notify_entry(f"Async {self.symbol}", price, self.sl_price, 100)
            await self.sync_sl_to_exchange(force_create=True)
        await self.persist_state()

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
            order = await self.adapter.create_order('limit', 'buy' if direction==1 else 'sell', self.quantity, target_price, {'postOnly': True})
            self.active_retest_order_id, self.sl_price = order['id'], sl_price
            await self.persist_state()
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
            order = await self.adapter.create_order('STOP_MARKET', 'buy' if direction==1 else 'sell', self.quantity, None, {'stopPrice': target_price})
            self.active_sniper_order_id = order['id']
            await self.persist_state()
        except Exception as e: self.logger.error(f"Sniper error: {e}")

    async def cancel_retest_order(self):
        if not self.active_retest_order_id: return
        try: await self.adapter.retry_api_call(self.adapter.exchange.cancel_order, self.active_retest_order_id, self.symbol)
        except: pass
        finally:
            self.active_retest_order_id = None
            await self.persist_state()

    async def cancel_sniper_ambush(self):
        if not self.active_sniper_order_id: return
        try: await self.adapter.cancel_trigger_order(self.active_sniper_order_id)
        except: pass
        finally:
            self.active_sniper_order_id = None
            await self.persist_state()

    async def check_retest_fill(self):
        if not self.active_retest_order_id: return
        try:
            o = await self.adapter.fetch_order(self.active_retest_order_id)
            if o['status'] == 'closed': await self.on_order_update({'i':o['id'], 'X':'FILLED', 'S':o['side'].upper(), 'z':o['filled'], 'ap':o['average']})
        except: pass

    async def check_sniper_fill(self):
        if not self.active_sniper_order_id: return
        try:
            o = await self.adapter.fetch_trigger_order(self.active_sniper_order_id)
            if o['status'] == 'closed': await self.on_order_update({'i':o['id'], 'X':'FILLED', 'S':o['side'].upper(), 'z':o['filled'], 'ap':o['average'] or o['price']})
        except: pass

    async def sync_all_orders(self):
        if self.settings["DRY_RUN"]: return
        try:
            self.logger.info(f"🔄 [{self.symbol}] Starting sync_all_orders...")
            positions = await self.adapter.fetch_positions()
            pos = next((p for p in positions if p['symbol'].replace('/', '').split(':')[0] == self.symbol.replace('/', '')), None)
            if pos and float(pos['contracts']) != 0:
                self.position = -1 if pos.get('side','').lower()=='short' or float(pos['contracts'])<0 else 1
                self.entry_price, self.quantity = float(pos['entryPrice']), abs(float(pos['contracts']))
                self.logger.info(f"💼 [{self.symbol}] Found active position: {self.position} (Qty: {self.quantity}, Entry: {self.entry_price})")
                if self.sl_price == 0 and self.df_indicators is not None:
                    row = self.df_indicators.iloc[-1]
                    self.sl_price = self.entry_price + (row['atr']*2.0)*(-self.position)
            else:
                self.logger.info(f"💼 [{self.symbol}] No active position found on exchange.")
                if self.position != 0:
                    self.logger.info(f"💼 [{self.symbol}] Bot position was {self.position}, resetting to 0 and canceling all orders.")
                    self.position = 0
                    await self.adapter.cancel_all_orders()
            if self.position != 0:
                orders = await self.adapter.get_all_open_orders()
                target_side = 'sell' if self.position == 1 else 'buy'
                all_sl_orders = []
                for o in orders:
                    is_stop = 'STOP' in str(o.get('type','')).upper() or o.get('stopPrice') or o.get('triggerPrice')
                    if is_stop and o.get('side','').lower()==target_side:
                        all_sl_orders.append(o)
                
                if all_sl_orders:
                    primary_sl = all_sl_orders[0]
                    self.sl_order_id = primary_sl['id']
                    self.sl_price = float(primary_sl.get('stopPrice', primary_sl.get('price', self.sl_price)))
                    self.last_sl_sync_price = self.sl_price
                    self.logger.info(f"🛡️ [{self.symbol}] Primary SL order matched on exchange: ID={self.sl_order_id}, Price={self.sl_price}")
                    
                    if len(all_sl_orders) > 1:
                        self.logger.warning(f"⚠️ [{self.symbol}] Found {len(all_sl_orders)} duplicate SL orders on exchange. Cleaning up duplicates...")
                        for dup_order in all_sl_orders[1:]:
                            try:
                                await self.adapter.cancel_trigger_order(dup_order['id'])
                                self.logger.info(f"🛡️ [{self.symbol}] Canceled duplicate SL order: {dup_order['id']}")
                            except Exception as ex:
                                self.logger.error(f"❌ [{self.symbol}] Failed to cancel duplicate SL order {dup_order['id']}: {ex}")
                else:
                    self.sl_order_id = None
                    self.last_sl_sync_price = 0
                    self.logger.warning(f"🛡️ [{self.symbol}] No matching SL order found on exchange.")
                    if self.sl_price > 0:
                        self.logger.info(f"🛡️ [{self.symbol}] Triggering SL creation/sync because SL price is valid ({self.sl_price:,.2f})...")
                        await self.sync_sl_to_exchange(force_create=True)
                    else:
                        self.logger.warning(f"⚠️ [{self.symbol}] Cannot create SL order on startup because SL price is 0.")
            else:
                self.sl_order_id = None
                self.last_sl_sync_price = 0
            if self.position == 0:
                orders = await self.adapter.get_all_open_orders()
                found_sniper = None
                found_retest = None
                for o in orders:
                    if 'STOP' in str(o.get('type', '')).upper() or o.get('stopPrice') or o.get('triggerPrice'):
                        found_sniper = o
                    elif str(o.get('type', '')).upper() == 'LIMIT':
                        found_retest = o
                if found_sniper:
                    self.active_sniper_order_id = found_sniper['id']
                    self.quantity = float(found_sniper.get('amount', self.quantity))
                    self.logger.info(f"🏹 [{self.symbol}] Found active Sniper order: ID={self.active_sniper_order_id}")
                else:
                    self.active_sniper_order_id = None
                if found_retest:
                    self.active_retest_order_id = found_retest['id']
                    self.quantity = float(found_retest.get('amount', self.quantity))
                    self.logger.info(f"🎣 [{self.symbol}] Found active Retest order: ID={self.active_retest_order_id}")
                else:
                    self.active_retest_order_id = None
            await self.persist_state()
        except Exception as e: self.logger.error(f"Sync error: {e}")

    async def sync_sl_to_exchange(self, force_create=False):
        if self.settings["DRY_RUN"]:
            self.sl_order_id = "DRY_SL"
            return
        if self.position == 0: return
        try:
            self.logger.info(f"🔄 [{self.symbol}] Starting sync_sl_to_exchange (force={force_create})...")
            if self.sl_order_id:
                try:
                    await self.adapter.cancel_trigger_order(self.sl_order_id)
                    self.logger.info(f"🛡️ [{self.symbol}] Canceled old SL order by ID: {self.sl_order_id}")
                except Exception as ex:
                    self.logger.warning(f"⚠️ [{self.symbol}] Could not cancel old SL ID {self.sl_order_id}: {ex}")
            orders = await self.adapter.get_all_open_orders()
            target_side = 'sell' if self.position == 1 else 'buy'
            for o in orders:
                is_stop = 'STOP' in str(o.get('type','')).upper() or o.get('stopPrice') or o.get('triggerPrice')
                if is_stop and o.get('side','').lower() == target_side:
                    try:
                        await self.adapter.cancel_trigger_order(o['id'])
                        self.logger.info(f"🛡️ [{self.symbol}] Canceled duplicate/existing SL order: {o['id']}")
                    except Exception as ex:
                        self.logger.error(f"❌ [{self.symbol}] Error canceling SL order {o['id']}: {ex}")
            params = {'stopPrice': self.sl_price, 'reduceOnly': True}
            self.logger.info(f"🛡️ [{self.symbol}] Creating new SL order at price {self.sl_price:,.2f} with qty {self.quantity}...")
            order = await self.adapter.create_order('STOP_MARKET', 'sell' if self.position == 1 else 'buy', self.quantity, None, params)
            self.sl_order_id, self.last_sl_sync_price = order['id'], self.sl_price
            await self.persist_state()
            self.notifier.send_message(f"🛡️ SL Sync: {self.symbol} -> {self.sl_price:,.2f}")
            self.logger.info(f"🛡️ [{self.symbol}] Successfully synced and placed new SL order: ID={self.sl_order_id}")
        except Exception as e:
            if "-2022" in str(e) or "ReduceOnly" in str(e):
                self.logger.warning(f"⚠️ ReduceOnly SL Sync rejected for {self.symbol}. Position may not exist on exchange. Syncing...")
                self.position = 0
                await self.persist_state()
                await self.sync_all_orders()
                return
            self.logger.error(f"SL Sync error: {e}")

    async def execute_entry(self, direction, atr):
        try:
            self.sl_price = self.last_price + (atr*2.0)*(-direction)
            qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
            if not qty or qty <= 0: return
            self.quantity = float(qty)
            if await self._is_over_safety_limit(self.quantity * self.last_price):
                self.logger.warning(f"⚠️ [{self.symbol}] Market entry blocked by Exposure Safety Limit check.")
                return
            if self.settings["DRY_RUN"]:
                self.entry_price = self.last_price
                await self._on_fill_success(direction, price=self.entry_price)
                return
            order = await self.adapter.create_market_order('buy' if direction == 1 else 'sell', self.quantity)
            self.entry_price = float(order.get('average') or order.get('price') or self.last_price) if isinstance(order, dict) else self.last_price
            await self._on_fill_success(direction, price=self.entry_price)
        except Exception as e: self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        try:
            if self.settings["DRY_RUN"]:
                await self._on_fill_success(0, is_exit=True, price=self.last_price)
                return
            order = await self.adapter.create_reduce_only_market_order('sell' if self.position == 1 else 'buy', self.quantity)
            exit_price = float(order.get('average') or order.get('price') or self.last_price) if isinstance(order, dict) else self.last_price
            await self._on_fill_success(0, is_exit=True, price=exit_price)
        except Exception as e:
            if "-2022" in str(e):
                self.position = 0
                await self.persist_state()
                await self.sync_all_orders()
                return
            self.logger.error(f"Exit error: {e}")

    async def force_exit(self):
        await self.adapter.cancel_all_orders()
        if self.position != 0: await self.execute_exit()

    async def persist_state(self):
        try:
            await _maybe_await(self.db.save_bot_state(
                self.symbol, self.position, self.entry_price, self.quantity,
                self.max_price_seen, self.min_price_seen, self.sl_price, self.sl_order_id,
                self.active_sniper_order_id, self.active_retest_order_id
            ))
        except Exception as e: self.logger.error(f"Persist error: {e}")

    def get_detailed_status(self):
        if self.df_indicators is None or self.df_indicators.empty:
            indicators_str = "  - Indicator Data: N/A"
        else:
            row = self.df_indicators.iloc[-1]
            cur_p = self.last_price
            ema_h = row.get('ema_h', 0)
            upper = row.get('upper', 0)
            lower = row.get('lower', 0)
            volume = row.get('volume', 0)
            avg_vol = row.get('avg_vol', 0)
            adx = row.get('adx', 0)
            adx_4h = row.get('adx_4h', 0)
            chop = row.get('chop', 0)
            chaos = row.get('chaos', 0)
            squeeze = row.get('squeeze', 0)
            ema_slope = row.get('ema_slope', 0)

            vol_mult = self.settings.get("VOL_MULTIPLIER", 2.2)
            adx_threshold = self.settings.get("ADX_FILTER_LEVEL", 20.0)
            adx_4h_threshold = self.settings.get("ADX_4H_THRESHOLD", 15.0)
            chaos_threshold = self.settings.get("CHAOS_THRESHOLD", 20.0)

            trend_status = "BULL 🚀" if cur_p > ema_h else "BEAR 📉"
            vol_status = "Burst 🔥" if volume > (avg_vol * vol_mult) else "Normal 💤"
            adx_status = "Trending 📈" if adx > adx_threshold else "Weak 📉"
            adx_4h_status = "Strong 📈" if adx_4h > adx_4h_threshold else "Weak 📉"
            chop_status = "Consolidating 🌀" if chop > 61.8 else ("Trending ⚡" if chop < 38.2 else "Normal ⚖️")
            chaos_status = "High 🌀" if chaos >= chaos_threshold else "Normal 💤"
            slope_status = "Positive 📈" if ema_slope > 0 else "Negative 📉"

            indicators_str = (
                f"  - Trend: {trend_status} (Price: {cur_p:,.4f} vs EMA: {ema_h:,.4f})\n"
                f"  - Donchian: Upper: {upper:,.4f} / Lower: {lower:,.4f}\n"
                f"  - Volume (1h): {volume:,.1f} (Target: {avg_vol * vol_mult:,.1f}, {vol_mult}x) -> {vol_status}\n"
                f"  - ADX (1h): {adx:.1f} (Target: {adx_threshold:.1f}) -> {adx_status}\n"
                f"  - ADX (4h): {adx_4h:.1f} (Target: {adx_4h_threshold:.1f}) -> {adx_4h_status}\n"
                f"  - Choppiness: {chop:.1f} (Target: 38.2-61.8) -> {chop_status}\n"
                f"  - Chaos Index: {chaos:.1f} (Target: {chaos_threshold:.1f}) -> {chaos_status}\n"
                f"  - Squeeze Score: {squeeze:.2f}\n"
                f"  - EMA Slope: {ema_slope:+.4f} -> {slope_status}"
            )

        if self.position != 0:
            pnl = ((self.last_price / self.entry_price) - 1) * 100 * self.position if self.entry_price != 0 else 0
            pos_name = "LONG 🟢" if self.position == 1 else "SHORT 🔴"
            return (
                f"• *{self.symbol}*: {pos_name}\n"
                f"  - 진입가: {self.entry_price:,.4f}\n"
                f"  - 수량: {self.quantity:.4f}\n"
                f"  - 손절가: {self.sl_price:,.4f}\n"
                f"  - 현재가: {self.last_price:,.4f}\n"
                f"  - 현재 PnL: {pnl:+.2f}%\n"
                f"{indicators_str}\n"
            )
        elif self.active_sniper_order_id:
            return (
                f"• *{self.symbol}*: SNIPER AMBUSH 🏹\n"
                f"  - 주문 ID: {self.active_sniper_order_id}\n"
                f"  - 손절가: {self.sl_price:,.4f}\n"
                f"  - 현재가: {self.last_price:,.4f}\n"
                f"{indicators_str}\n"
            )
        elif self.active_retest_order_id:
            return (
                f"• *{self.symbol}*: RETEST AMBUSH 🎣\n"
                f"  - 주문 ID: {self.active_retest_order_id}\n"
                f"  - 손절가: {self.sl_price:,.4f}\n"
                f"  - 현재가: {self.last_price:,.4f}\n"
                f"{indicators_str}\n"
            )
        else:
            return (
                f"• *{self.symbol}*: IDLE 💤\n"
                f"  - 현재가: {self.last_price:,.4f}\n"
                f"{indicators_str}\n"
            )

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
    db, notifier = AsyncDBManager(), TelegramNotifier()
    notifier.set_commands()
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
