import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import logging
import signal
import time
from datetime import datetime, timedelta
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
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
        self.lock = asyncio.Lock() # 심볼별 메시지 처리 순차 보장용 락
        
        self.settings = CONFIG.copy()
        if "SYMBOL_SETTINGS" in CONFIG and self.symbol in CONFIG["SYMBOL_SETTINGS"]:
            self.settings.update(CONFIG["SYMBOL_SETTINGS"][self.symbol])
        
        # Strategy Engine Instance
        self.engine = TrendCrusherV2(config=self.settings)
        
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.sl_order_id = None
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.is_halted = False 
        self.pending_settings = None 
        self.active_sniper_order_id = None 
        self.use_sniper = self.settings.get("USE_SNIPER", True) 
        self.active_retest_order_id = None 
        self.use_retest_maker = self.settings.get("USE_RETEST_MAKER", False) 
        self.retest_order_ts = None 
        self.is_processing_fill = False # 진입/체결 처리 중복 방지 플래그
        
        self.ohlcv_1h = None
        self.ohlcv_4h = None
        self.last_price = 0
        self.df_indicators = None
        
        # Throttling & Sync states
        self.last_db_record_ts = 0
        self.last_indicator_calc_ts = 0
        self.last_sl_sync_price = 0
        self.last_fill_poll_ts = 0

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

    async def fetch_ohlcv(self, tf, limit=100):
        ohlcv = await self.retry_api_call(self.exchange.fetch_ohlcv, self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def fetch_trigger_order(self, order_id):
        # Binance futures STOP_MARKET orders are conditional/algo orders and
        # must be queried through the trigger-order endpoint.
        return await self.retry_api_call(
            self.exchange.fetch_order,
            order_id,
            self.symbol,
            params={'trigger': True},
        )

    async def cancel_trigger_order(self, order_id):
        return await self.retry_api_call(
            self.exchange.cancel_order,
            order_id,
            self.symbol,
            params={'trigger': True},
        )

    async def create_reduce_only_market_order(self, side, amount):
        return await self.retry_api_call(
            self.exchange.create_order,
            self.symbol,
            'market',
            side,
            amount,
            None,
            params={'reduceOnly': True},
        )

    async def manage_retest_ambush(self, direction, target_price, sl_price):
        if self.active_retest_order_id: return
        qty = await self.pm.calculate_order_qty(self.symbol, target_price, sl_price)
        if qty is None or (isinstance(qty, (int, float)) and qty <= 0): return
        
        self.quantity = float(qty)
        side = 'buy' if direction == 1 else 'sell'
        try:
            if self.settings["DRY_RUN"]:
                self.active_retest_order_id = "DRY_RETEST"
                self.entry_price = target_price if direction == 1 else -target_price
            else:
                # [Margin Safety Guard]
                balance = await self.retry_api_call(self.exchange.fetch_balance)
                quote_currency = self.symbol.split('/')[-1]
                available_margin = float(balance.get(quote_currency, {}).get('free', 0))
                leverage = self.settings.get("MAX_LEVERAGE", 1)
                required_margin = (self.quantity * target_price) / leverage
                
                if required_margin > available_margin * 0.95:
                    old_qty = self.quantity
                    self.quantity = (available_margin * 0.95 * leverage) / target_price
                    self.quantity = float(self.exchange.amount_to_precision(self.symbol, self.quantity))
                    self.logger.warning(f"⚠️ Margin Guard (Retest): Reduced Qty {old_qty} -> {self.quantity}")
                    if self.quantity <= 0: return

                self.logger.info(f"🎣 Retest MAKER: {side.upper()} at {target_price:,.2f}")
                order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'limit', side, self.quantity, target_price, {'postOnly': True})
                self.active_retest_order_id = order['id']
                self.persist_state()
            self.retest_order_ts, self.sl_price = datetime.now(), sl_price
        except Exception as e: self.logger.error(f"Retest error: {e}")

    async def manage_sniper_ambush(self, direction, target_price, atr):
        if self.active_sniper_order_id: return
        self.sl_price = target_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else target_price + (atr * self.settings["INITIAL_SL_ATR"])
        qty = await self.pm.calculate_order_qty(self.symbol, target_price, self.sl_price)
        if qty is None or (isinstance(qty, (int, float)) and qty <= 0): return
        
        self.quantity = float(qty)
        side = 'buy' if direction == 1 else 'sell'
        try:
            if self.settings["DRY_RUN"]:
                self.active_sniper_order_id = "DRY_SNIPER"
            else:
                # [Margin Safety Guard]
                balance = await self.retry_api_call(self.exchange.fetch_balance)
                quote_currency = self.symbol.split('/')[-1]
                available_margin = float(balance.get(quote_currency, {}).get('free', 0))
                leverage = self.settings.get("MAX_LEVERAGE", 1)
                required_margin = (self.quantity * target_price) / leverage
                
                if required_margin > available_margin * 0.95:
                    old_qty = self.quantity
                    self.quantity = (available_margin * 0.95 * leverage) / target_price
                    self.quantity = float(self.exchange.amount_to_precision(self.symbol, self.quantity))
                    self.logger.warning(f"⚠️ Margin Guard (Sniper): Reduced Qty {old_qty} -> {self.quantity}")
                    if self.quantity <= 0: return

                self.logger.info(f"🏹 Sniper STOP_MARKET: {side.upper()} at {target_price:,.2f}")
                params = {'stopPrice': target_price, 'reduceOnly': False}
                order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', side, self.quantity, None, params)
                self.active_sniper_order_id = order['id']
                self.persist_state()
        except Exception as e: self.logger.error(f"Sniper error: {e}")

    async def cancel_retest_order(self):
        if not self.active_retest_order_id: return
        try:
            if not self.settings["DRY_RUN"]:
                # Verify existence before cancel to prevent -1102
                try:
                    order = await self.retry_api_call(self.exchange.fetch_order, self.active_retest_order_id, self.symbol)
                    if order['status'] in ['open', 'untouched', 'partially_filled']:
                        await self.retry_api_call(self.exchange.cancel_order, self.active_retest_order_id, self.symbol)
                        self.logger.info(f"🎣 Retest order {self.active_retest_order_id} cancelled.")
                    else:
                        self.logger.info(f"🎣 Retest order {self.active_retest_order_id} already {order['status']}. Clearing state.")
                except ccxt.OrderNotFound:
                    self.logger.info(f"🎣 Retest order {self.active_retest_order_id} not found on exchange. Clearing state.")
        except Exception as e:
            self.logger.warning(f"Failed to cancel retest order for {self.symbol}: {e}")
        finally:
            self.active_retest_order_id = None
            self.retest_order_ts = None
            self.persist_state()

    async def cancel_sniper_ambush(self):
        if not self.active_sniper_order_id: return
        try:
            if not self.settings["DRY_RUN"]:
                # Sniper (STOP_MARKET) needs trigger-order fetch
                try:
                    order = await self.fetch_trigger_order(self.active_sniper_order_id)
                    if order['status'] in ['open', 'untouched', 'partially_filled']:
                        await self.cancel_trigger_order(self.active_sniper_order_id)
                        self.logger.info(f"♻️ Sniper Cancelled for {self.symbol}")
                    else:
                        self.logger.info(f"♻️ Sniper {self.active_sniper_order_id} already {order['status']}. Clearing state.")
                except ccxt.OrderNotFound:
                    self.logger.info(f"♻️ Sniper order {self.active_sniper_order_id} not found on exchange. Clearing state.")
                except Exception as e:
                    if "-1102" in str(e):
                        self.logger.error(f"❌ Malformed Sniper ID {self.active_sniper_order_id}. Clearing state.")
                    else: raise e
            else:
                self.logger.info(f"♻️ Dry Sniper state cleared for {self.symbol}")
        except Exception as e:
            self.logger.warning(f"Sniper cancel error for {self.symbol}: {e}")
        finally:
            self.active_sniper_order_id = None
            self.persist_state()

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
                self.logger.info(f"💾 Recovered: Pos={self.position}, Entry={self.entry_price}, Sniper={self.active_sniper_order_id}")

            self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"], limit=500)
            self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"], limit=500)
            
            self._update_indicators()
            
            # --- [BACKFILL] Populate history_1h with last 48h of already computed data ---
            if self.df_indicators is not None and not self.df_indicators.empty:
                self.logger.info(f"💾 Backfilling 48h history for {self.symbol}...")
                # Get the last 48 rows (hourly bars) from the computed indicators
                history_slice = self.df_indicators.tail(48)
                saved_count = 0
                for idx, row in history_slice.iterrows():
                    try:
                        # Extract timestamp from index (Pandas DatetimeIndex expected)
                        ts_str = idx.strftime("%Y-%m-%d %H:%M:%S")

                        # Using correct engine columns: ema_h, upper, lower
                        self.db.log_history_1h(
                            self.symbol,
                            ts_str,
                            float(row['close']),
                            float(row['ema_h']),
                            float(row['upper']),
                            float(row['lower']),
                            float(row['volume']),
                            float(row['adx'])
                        )
                        saved_count += 1
                    except Exception as e:
                        self.logger.debug(f"Skip row: {e}")
                self.logger.info(f"📊 {saved_count} hourly rows backfilled for {self.symbol}")
            else:
                self.logger.warning(f"⚠️ Indicators initialized but df is empty for {self.symbol}")
            
            # [CRITICAL] Record initial status to DB for dashboard visibility
            asyncio.create_task(self._record_live_status())
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize {self.symbol}: {e}")
            raise e

    def _update_indicators(self, is_live=False):
        if self.ohlcv_1h is not None and self.ohlcv_4h is not None:
            self.df_indicators = self.engine.calculate_indicators(self.ohlcv_1h, self.ohlcv_4h, self.settings, is_live=is_live)

    async def on_kline_update(self, tf, kline):
        async with self.lock:
            try:
                signal_tf = self.settings["SIGNAL_TIMEFRAME"]
                trend_tf = self.settings["TREND_TIMEFRAME"]
                if tf not in [signal_tf, trend_tf]: return

                is_signal_tf = (tf == signal_tf)
                target_df = self.ohlcv_1h if is_signal_tf else self.ohlcv_4h
                if target_df is None: return

                kline_ts = pd.to_datetime(kline['t'], unit='ms')
                self.last_price = float(kline['c'])
                
                last_idx = target_df.index[-1]
                if kline_ts == target_df.loc[last_idx, 'timestamp']:
                    target_df.loc[last_idx, ['open', 'high', 'low', 'close', 'volume']] = [
                        float(kline['o']), float(kline['h']), float(kline['l']), self.last_price, float(kline['v'])
                    ]
                elif kline_ts > target_df.loc[last_idx, 'timestamp']:
                    if is_signal_tf: self.ohlcv_1h = await self.fetch_ohlcv(tf)
                    else: self.ohlcv_4h = await self.fetch_ohlcv(tf)
                    self.logger.info(f"🕯️ New Candle ({tf}) synced at {kline_ts}")
                
                now = time.time()
                if kline['x'] or (now - self.last_indicator_calc_ts > 10):
                    self._update_indicators(is_live=True)
                    self.last_indicator_calc_ts = now
                    
                    if kline['x'] and tf == signal_tf:
                        last_row = self.df_indicators.iloc[-1]
                        try:
                            self.db.log_history_1h(
                                self.symbol,
                                self.df_indicators.index[-1].strftime("%Y-%m-%d %H:%M:%S"),
                                float(last_row['close']),
                                float(last_row['ema_h']),
                                float(last_row['upper']),
                                float(last_row['lower']),
                                float(last_row['volume']),
                                float(last_row['adx'])
                            )
                            self.logger.info(f"💾 Hourly snapshot logged for {self.symbol}")
                        except Exception as e:
                            self.logger.error(f"Error logging hourly snapshot: {e}")
                    
                    asyncio.create_task(self._record_live_status())

                if not kline['x']:
                    if self.position != 0: await self.check_exit()
                    else: await self.check_entry()
            except Exception as e:
                self.logger.error(f"⚠️ Error updating OHLCV buffer for {self.symbol}: {e}")

    async def on_order_update(self, order_data):
        async with self.lock:
            try:
                order_id = str(order_data['i'])
                symbol = order_data['s']
                status = order_data['X']
                side = order_data['S'].lower()
                qty = float(order_data['z'])
                avg_price = float(order_data.get('ap', order_data['L'])) 
                
                self.logger.info(f"📝 WS Order Update: {symbol} {side} {status} (ID: {order_id}, Qty: {qty}, Price: {avg_price:,.2f})")
                
                if status == 'FILLED':
                    if order_id in [str(self.active_sniper_order_id), str(self.active_retest_order_id)]:
                        if avg_price == 0:
                            self.logger.warning(f"⚠️ Ambush filled via WS but avg_price is 0! Using last_price {self.last_price}")
                            avg_price = self.last_price
                        self.logger.info(f"🎯 Ambush FILLED via WS: {symbol} {side} at {avg_price:,.2f}")
                        self.quantity, self.entry_price = qty, avg_price
                        direction = 1 if side == 'buy' else -1
                        await self._on_fill_success(direction)
                        self.active_sniper_order_id = self.active_retest_order_id = None
                    
                    elif order_id == str(self.sl_order_id) or (self.position != 0 and side != ('buy' if self.position == 1 else 'sell')):
                        self.logger.info(f"🛡️ Exit/SL FILLED via WS: {symbol} {side} at {avg_price:,.2f}")
                        
                        if self.entry_price == 0: self.entry_price = self.last_price or avg_price
                        pnl_pct = ((avg_price / self.entry_price) - 1) * 100 * self.position
                        pnl_usdt = (avg_price - self.entry_price) * qty * self.position
                        
                        self.db.log_trade_close(self.symbol, avg_price, pnl_pct, pnl_usdt)
                        await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
                        
                        self.position = 0; self.entry_price = 0; self.quantity = 0; self.sl_price = 0
                        self.sl_order_id = self.active_sniper_order_id = self.active_retest_order_id = None
                        self.max_price_seen = 0; self.min_price_seen = float('inf')
                        self.persist_state()
                        self.notifier.notify_exit(f"SL/Exit {self.symbol}", avg_price, pnl_pct, pnl_usdt)
                        asyncio.create_task(self.sync_all_orders())
                
                elif status == 'CANCELED':
                    if order_id == str(self.sl_order_id):
                        self.logger.warning(f"⚠️ SL Order {order_id} was CANCELED externally!")
                        self.sl_order_id = None
                    elif order_id == str(self.active_sniper_order_id):
                        self.active_sniper_order_id = None
                        self.persist_state()
                    elif order_id == str(self.active_retest_order_id):
                        self.active_retest_order_id = None
                        self.persist_state()
            except Exception as e:
                self.logger.error(f"Error in on_order_update: {e}")

    async def _record_live_status(self):
        if self.df_indicators is None or self.df_indicators.empty: return
        try:
            row = self.df_indicators.iloc[-1]
            last_price = self.last_price
            vol_target = row['avg_vol'] * self.settings.get('VOL_MULTIPLIER', 2.0)
            vol_ratio = min(1.0, row['volume'] / vol_target) if vol_target > 0 else 0
            adx_target = self.settings.get('ADX_FILTER_LEVEL', 25.0)
            adx_ratio = min(1.0, row['adx'] / adx_target) if adx_target > 0 else 0
            upper, lower = row['upper'], row['lower']
            ema = row['ema_h']
            prox_pct = self.settings.get('SNIPER_PROXIMITY_PCT', 0.005)
            trend_ok, prox_ratio = False, 0
            if last_price > ema:
                trend_ok = True
                dist = abs(upper - last_price)
                prox_limit = upper * prox_pct
                prox_ratio = max(0, 1.0 - (dist / prox_limit)) if prox_limit > 0 else 0
            elif last_price < ema:
                trend_ok = True
                dist = abs(lower - last_price)
                prox_limit = lower * prox_pct
                prox_ratio = max(0, 1.0 - (dist / prox_limit)) if prox_limit > 0 else 0
            if (last_price >= upper and trend_ok) or (last_price <= lower and trend_ok): prox_ratio = 1.0
            score = (prox_ratio * 40) + (vol_ratio * 30) + (adx_ratio * 30)
            if not trend_ok: score *= 0.5
            self.db.update_live_status(self.symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, score, last_price, upper, lower, float(row['adx']), float(ema))
        except Exception as e: self.logger.error(f"Error recording live status: {e}")

    async def _on_fill_success(self, direction):
        if self.is_processing_fill: return
        self.is_processing_fill = True
        
        side_str = "LONG" if direction == 1 else "SHORT"
        try:
            # [CRITICAL] 포지션 상태를 '즉시' 업데이트하여 중복 진입 차단
            self.position = direction
            self.max_price_seen = self.min_price_seen = self.entry_price
            
            if not self.settings["DRY_RUN"]:
                params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
                self.sl_order_id = sl_order['id']
            else: self.sl_order_id = "DRY_SL"
            
            self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
            self.persist_state()
            self.notifier.notify_entry(f"🚀 {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)
        except Exception as sl_err:
            self.logger.error(f"🚨 CRITICAL: SL failed: {sl_err}. EMERGENCY LIQUIDATION!")
            if not self.settings["DRY_RUN"]:
                await self.create_reduce_only_market_order('sell' if direction == 1 else 'buy', self.quantity)
            self.position = 0 # 실패 시 초기화
        finally:
            self.is_processing_fill = False

    async def check_sniper_fill(self):
        if self.settings["DRY_RUN"] or not self.active_sniper_order_id: return
        try:
            order = await self.fetch_trigger_order(self.active_sniper_order_id)
            if order and isinstance(order, dict) and order.get('status') == 'closed':
                self.logger.info(f"🎯 Sniper Order FILLED for {self.symbol} (Polled)!")
                self.quantity = float(order.get('filled') or order.get('amount') or self.quantity)
                
                # [CRITICAL] Ensure entry_price is not zero
                avg_p = float(order.get('average') or order.get('price') or 0)
                if avg_p == 0:
                    self.logger.warning(f"⚠️ Sniper filled but API returned 0 price. Using last_price {self.last_price}")
                    avg_p = self.last_price
                
                self.entry_price = avg_p
                direction = 1 if order.get('side') == 'buy' else -1
                await self._on_fill_success(direction)
                self.active_sniper_order_id = None
                self.persist_state()
        except ccxt.OrderNotFound:
            self.logger.warning(f"⚠️ Sniper Order {self.active_sniper_order_id} not found on exchange. Clearing state.")
            self.active_sniper_order_id = None
            self.persist_state()
        except Exception as e: self.logger.error(f"Error checking sniper fill: {e}")

    async def check_retest_fill(self):
        if not self.active_retest_order_id: return
        if self.retest_order_ts and (datetime.now() - self.retest_order_ts).total_seconds() > 14400:
            self.logger.info(f"⌛ Retest order TIMEOUT (4h) for {self.symbol}. Cancelling."); await self.cancel_retest_order(); return
        if self.settings["DRY_RUN"]: return
        try:
            order = await self.retry_api_call(self.exchange.fetch_order, self.active_retest_order_id, self.symbol)
            if order and isinstance(order, dict) and order.get('status') == 'closed':
                self.logger.info(f"✅ Retest Maker Order FILLED for {self.symbol} (Polled)!")
                self.quantity = float(order.get('filled') or order.get('amount') or self.quantity)
                self.entry_price = float(order.get('average') or order.get('price') or self.entry_price)
                direction = 1 if order.get('side') == 'buy' else -1
                await self._on_fill_success(direction)
                self.active_retest_order_id = None
                self.retest_order_ts = None
                self.persist_state()
        except ccxt.OrderNotFound:
            self.logger.warning(f"⚠️ Retest Order {self.active_retest_order_id} not found on exchange. Clearing state.")
            self.active_retest_order_id = None
            self.retest_order_ts = None
            self.persist_state()
        except Exception as e: self.logger.error(f"Error checking retest fill: {e}")

    async def sync_all_orders(self):
        """Gap-filling sync: Check all pending orders and actual position via REST API."""
        if self.settings["DRY_RUN"]: return
        self.logger.info(f"🔍 Syncing all orders & position for {self.symbol}...")
        try:
            # 1. Sync Actual Position from Exchange
            # Fetch all positions to ensure we catch symbols with settlement suffixes like :USDT
            positions = await self.retry_api_call(self.exchange.fetch_positions)
            
            # Flexible matching: ETH/USDT should match ETH/USDT:USDT or ETHUSDT
            pos = None
            for p in positions:
                p_sym = p['symbol']
                if p_sym == self.symbol or \
                   p_sym.replace(':USDT', '') == self.symbol or \
                   p_sym.replace('/', '') == self.symbol.replace('/', ''):
                    pos = p
                    break
            
            if pos and float(pos['contracts']) != 0:
                actual_qty = abs(float(pos['contracts']))
                actual_entry = float(pos['entryPrice'])
                actual_side = 1 if float(pos['contracts']) > 0 else -1
                
                if self.position != actual_side or abs(self.entry_price - actual_entry) > 0.1 or abs(self.quantity - actual_qty) > 0.0001:
                    self.logger.info(f"🔄 State Repaired for {self.symbol}: Pos {self.position}->{actual_side}, Entry {self.entry_price:.2f}->{actual_entry:.2f}, Qty {self.quantity}->{actual_qty}")
                    self.position, self.entry_price, self.quantity = actual_side, actual_entry, actual_qty
                    self.max_price_seen = max(self.max_price_seen, self.entry_price) if self.position == 1 else self.max_price_seen
                    self.min_price_seen = min(self.min_price_seen, self.entry_price) if self.position == -1 else self.min_price_seen
                    self.persist_state()
            elif self.position != 0:
                # Exchange says no position, but bot thinks we have one
                # ONLY reset if we actually got a valid response from the exchange containing other data
                if positions is not None and len(positions) > 0:
                    self.logger.warning(f"⚠️ Exchange confirmed NO position for {self.symbol}, but bot state is {self.position}. Resetting bot state.")
                    self.position = 0; self.entry_price = 0; self.quantity = 0; self.sl_order_id = None
                    self.persist_state()
                else:
                    self.logger.warning(f"⚠️ Could not verify position for {self.symbol} (empty exchange response). Skipping state reset.")

            # 2. Check Sniper & Retest fills
            if self.active_sniper_order_id: await self.check_sniper_fill()
            if self.active_retest_order_id: await self.check_retest_fill()
            
            # 3. Check StopLoss status
            if self.sl_order_id and self.position != 0:
                try:
                    order = await self.fetch_trigger_order(self.sl_order_id)
                    if order and order['status'] == 'closed':
                        avg_p = float(order.get('average', order.get('price', 0)))
                        qty = float(order.get('filled', order.get('amount', 0)))
                        self.logger.info(f"🛡️ SL Sync: Detected SL fill (REST) at {avg_p}")
                        await self.on_order_update({
                            'i': self.sl_order_id, 
                            's': self.symbol.replace('/', ''), 
                            'X': 'FILLED', 
                            'S': order['side'].upper(), 
                            'z': qty, 
                            'ap': avg_p
                        })
                except:
                    self.logger.warning(f"Could not fetch SL order {self.sl_order_id}. It might have been deleted.")
                    self.sl_order_id = None
        except Exception as e:
            self.logger.error(f"Error during order/pos sync for {self.symbol}: {e}")

    async def check_entry(self):
        if self.is_halted or self.df_indicators is None: return
        row = self.df_indicators.iloc[-1]
        is_ambushing = bool(self.active_sniper_order_id or self.active_retest_order_id)
        sig_type, target_p, sl_p = self.engine.check_entry_signal(row, self.last_price, self.use_sniper, self.use_retest_maker, self.settings, is_ambushing=is_ambushing)
        if sig_type is None:
            if self.active_sniper_order_id: self.logger.info(f"🚫 Sniper weakened. Aborting {self.symbol}."); await self.cancel_sniper_ambush()
            if self.active_retest_order_id: self.logger.info(f"🚫 Retest conditions weakened. Aborting {self.symbol}."); await self.cancel_retest_order()
            return
        if self.active_retest_order_id: return 
        if sig_type == 'RETEST': direction = 1 if target_p > row['ema_h'] else -1; await self.manage_retest_ambush(direction, target_p, sl_p)
        elif sig_type == 'SNIPER': direction = 1 if target_p > row['ema_h'] else -1; await self.manage_sniper_ambush(direction, target_p, row['atr'])
        elif sig_type == 'MARKET': direction = 1 if target_p > row['ema_h'] else -1; await self.execute_entry(direction, row['atr'])

    async def on_mark_price_update(self, price):
        async with self.lock:
            self.last_price = price
            now = time.time()
            if now - self.last_db_record_ts > 5: await self._record_live_status(); self.last_db_record_ts = now
            if now - self.last_fill_poll_ts > 30:
                if self.active_sniper_order_id: await self.check_sniper_fill()
                if self.active_retest_order_id: await self.check_retest_fill()
                self.last_fill_poll_ts = now
            if self.position != 0 or self.is_processing_fill: 
                await self.check_exit()
            else:
                if self.settings["DRY_RUN"] and self.active_retest_order_id:
                    is_filled = (self.entry_price > 0 and price <= self.entry_price) or (self.entry_price < 0 and price >= abs(self.entry_price))
                    if is_filled:
                        self.logger.info(f"🧪 [DRY RUN] Retest Maker FILLED at {price}")
                        direction = 1 if self.entry_price > 0 else -1
                        self.entry_price = abs(self.entry_price)
                        await self._on_fill_success(direction)
                        self.active_retest_order_id = None
                await self.check_entry()

    async def check_exit(self):
        if self.df_indicators is None or self.position == 0: return
        
        # 1. State Validation: If position exists but no SL order is active
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

        # 1. Update Peak Prices first to ensure current tick is reflected
        if self.position == 1: self.max_price_seen = max(self.max_price_seen, self.last_price)
        else: self.min_price_seen = min(self.min_price_seen, self.last_price)

        row = self.df_indicators.iloc[-1]
        state = {
            'position': self.position, 
            'entry_price': self.entry_price, 
            'max_price_seen': self.max_price_seen, 
            'min_price_seen': self.min_price_seen, 
            'sl_price': self.sl_price
        }

        # 2. Update trailing SL logic via strategy engine
        # check_exit_signal will update state['sl_price'] if trailing conditions are met
        is_exit_triggered = self.engine.check_exit_signal(row, self.last_price, state, self.settings)
        
        # Update local values from engine result
        self.sl_price = state['sl_price']

        # 3. Handle Exit Condition
        if is_exit_triggered:
            # [FAIL-SAFE] 만약 현재가가 손절가에 도달했는데, 거래소 주문이 아직 예전 가격(동기화 전)에 머물러 있다면
            # 거래소 체결을 기다리지 않고 즉시 시장가로 탈출하여 수익을 보존합니다.
            sync_diff = abs(self.sl_price - self.last_sl_sync_price) / (self.last_sl_sync_price or 1)
            if sync_diff > 0.0005: # 0.05% 이상 차이날 경우 동기화 전으로 판단
                self.logger.warning(f"🚨 {self.symbol} SL Hit ({self.last_price:,.2f}) before Exchange Sync (Diff: {sync_diff:.4f}). Emergency Market Exit!")
                await self.execute_exit()
                return

            # 일반적인 경우(동기화 완료)에는 거래소의 SL 주문이 체결되기를 기다립니다.
            if (self.position == 1 and self.last_price <= self.sl_price) or \
               (self.position == -1 and self.last_price >= self.sl_price):
                self.logger.info(f"⏳ {self.symbol} price {self.last_price:,.2f} hit SL {self.sl_price:,.2f}. Waiting for exchange FILL event...")
                return

        # 4. Sync Trailing SL to exchange if it moved significantly
        if abs(self.sl_price - self.last_sl_sync_price) / (self.last_sl_sync_price or 1) > 0.0005: 
            await self.sync_sl_to_exchange()

    async def sync_sl_to_exchange(self, force_create=False):
        if self.settings["DRY_RUN"] or self.position == 0 or self.quantity <= 0:
            return
            
        if not self.sl_order_id and not force_create:
            return

        # Capture current state into local variables to prevent race conditions 
        target_sl = self.sl_price
        target_qty = self.quantity
        target_side = 'sell' if self.position == 1 else 'buy'
        
        try:
            self.logger.info(f"🔄 Syncing SL for {self.symbol} -> {target_sl:,.2f} (Qty: {target_qty})")
            if self.sl_order_id:
                try: await self.cancel_trigger_order(self.sl_order_id)
                except: pass
            
            # Use captured local variables for the actual API call
            params = {'stopPrice': target_sl, 'reduceOnly': True}
            sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', target_side, target_qty, None, params)
            self.sl_order_id, self.last_sl_sync_price = sl_order['id'], target_sl
            self.persist_state()
            
            # 성공 시 텔레그램 알림 발송
            self.notifier.send_message(
                f"🛡️ **SL Updated: {self.symbol}**\n"
                f"- New SL: `{target_sl:,.2f}`\n"
                f"- Mark Price: `{self.last_price:,.2f}`"
            )
        except Exception as e: self.logger.error(f"❌ SL Sync Failed for {self.symbol}: {e}")

    async def execute_entry(self, direction, atr):
        side_str = "LONG" if direction == 1 else "SHORT"
        self.sl_price = float(self.last_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else self.last_price + (atr * self.settings["INITIAL_SL_ATR"]))
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if qty is None or qty <= 0: return
        self.quantity = float(qty)
        try:
            if not self.settings["DRY_RUN"]:
                balance = await self.retry_api_call(self.exchange.fetch_balance)
                quote = self.symbol.split('/')[-1]
                avail = float(balance.get(quote, {}).get('free', 0))
                leverage = self.settings.get("MAX_LEVERAGE", 1)
                if (self.quantity * self.last_price) / leverage > avail * 0.95:
                    self.quantity = float(self.exchange.amount_to_precision(self.symbol, (avail * 0.95 * leverage) / self.last_price))
                    if self.quantity <= 0: return
                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                if pos and float(pos['contracts']) != 0:
                    self.position, self.entry_price, self.quantity = (1 if float(pos['contracts']) > 0 else -1), float(pos['entryPrice']), abs(float(pos['contracts']))
                    self.persist_state(); return
                order = await self.exchange.create_market_order(self.symbol, 'buy' if direction == 1 else 'sell', self.quantity)
                if order and isinstance(order, dict):
                    self.entry_price = float(order.get('average') or order.get('price') or self.last_price)
                    self.quantity = float(order.get('filled') or self.quantity)
                try:
                    params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                    sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
                    self.sl_order_id = sl_order['id']
                except:
                    await self.create_reduce_only_market_order('sell' if direction == 1 else 'buy', self.quantity)
                    return
            else: self.entry_price = self.last_price
            self.position = direction
            self.max_price_seen = self.min_price_seen = self.entry_price
            self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
            self.persist_state()
            self.notifier.notify_entry(f"Async {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)
        except Exception as e: self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        if self.position == 0: return
        try:
            exit_price = self.last_price
            if not self.settings["DRY_RUN"]:
                order = await self.create_reduce_only_market_order('sell' if self.position == 1 else 'buy', self.quantity)
                await asyncio.sleep(1)
                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                if pos and float(pos['contracts']) != 0:
                    await self.create_reduce_only_market_order('sell' if self.position == 1 else 'buy', abs(float(pos['contracts'])))
                if order and isinstance(order, dict): exit_price = float(order.get('average') or order.get('price') or self.last_price)
                try:
                    if self.sl_order_id: await self.cancel_trigger_order(self.sl_order_id)
                except: pass
            pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
            pnl_usdt = (exit_price - self.entry_price) * self.quantity * self.position
            self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
            await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
            self.logger.info(f"✅ Trade Closed: {self.symbol} at {exit_price:,.2f} ({pnl_pct:+.2f}%)")
            self.notifier.notify_exit(f"Async {self.symbol}", exit_price, pnl_pct, pnl_usdt)
            self.position = 0; self.entry_price = 0; self.quantity = 0; self.sl_price = 0; self.sl_order_id = None; self.max_price_seen = 0; self.min_price_seen = float('inf'); self.persist_state()
        except Exception as e: self.logger.error(f"Exit error: {e}")

    async def force_exit(self):
        try:
            self.logger.info(f"🚨 FORCE EXIT Triggered for {self.symbol}")
            positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
            pos = next((p for p in positions if p['symbol'] == self.symbol), None)
            exit_price = self.last_price
            if pos and float(pos['contracts']) != 0:
                side = 'sell' if float(pos['contracts']) > 0 else 'buy'
                order = await self.create_reduce_only_market_order(side, abs(float(pos['contracts'])))
                if order and isinstance(order, dict): exit_price = float(order.get('average') or order.get('price') or exit_price)
            await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol)
            if self.position != 0:
                pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
                pnl_usdt = (exit_price - self.entry_price) * self.quantity * self.position
                self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
                await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
                self.notifier.notify_exit(f"🚨 FORCE {self.symbol}", exit_price, pnl_pct, pnl_usdt)
            self.position = 0; self.entry_price = 0; self.quantity = 0; self.sl_price = 0; self.sl_order_id = None; self.max_price_seen = 0; self.min_price_seen = float('inf'); self.persist_state()
        except Exception as e: self.logger.error(f"❌ Force exit failed for {self.symbol}: {e}")

    def get_detailed_status(self):
        if self.df_indicators is None or self.df_indicators.empty: return f"• **{self.symbol}**: No data."
        row = self.df_indicators.iloc[-1]
        pos_str = "IDLE"
        if self.position == 1: pos_str = "🟢 LONG"
        elif self.position == -1: pos_str = "🔴 SHORT"

        # Guard against zero entry price to prevent float division by zero
        pnl_str = ""
        if self.position != 0 and self.entry_price != 0:
            pnl_str = f" ({(((self.last_price / self.entry_price) - 1) * 100 * self.position):+.2f}%)"

        ambush = "🎯 Sniper" if self.active_sniper_order_id else ("🎣 Retest" if self.active_retest_order_id else "None")
        upper, lower, ema, adx = row['upper'], row['lower'], row['ema_h'], row['adx']
        vol_target = row['avg_vol'] * self.settings.get('VOL_MULTIPLIER', 2.0)
        vol_ratio = (row['volume'] / vol_target * 100) if vol_target > 0 else 0
        prox_pct = self.settings.get('SNIPER_PROXIMITY_PCT', 0.005)
        dist = abs((upper if self.last_price > ema else lower) - self.last_price)
        prox = max(0, 1.0 - (dist / ((upper if self.last_price > ema else lower) * prox_pct))) * 100 if prox_pct > 0 else 0
        return f"• **{self.symbol}**: {pos_str}{pnl_str}\n  - Price: {self.last_price:,.2f} | EMA: {ema:,.2f}\n  - Bands: [{lower:,.2f} ~ {upper:,.2f}]\n  - Filters: Vol {vol_ratio:.1f}% | ADX {adx:.1f} | Prox {prox:.1f}%\n  - Ambush: {ambush}\n"

    def persist_state(self):
        try: self.db.save_bot_state(self.symbol, self.position, self.entry_price, self.quantity, self.max_price_seen, self.min_price_seen, self.sl_price, self.sl_order_id, self.active_sniper_order_id, self.active_retest_order_id)
        except Exception as e: self.logger.error(f"Failed to persist state: {e}")

async def handle_commands(bots, notifier, pm):
    from src.optimizer_engine import OptimizerEngine
    offset = None
    try:
        initial_updates = notifier.get_updates(offset)
        if initial_updates and initial_updates.get("ok") and initial_updates.get("result"): offset = initial_updates["result"][-1]["update_id"] + 1
    except: pass
    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset, msg = update["update_id"] + 1, update.get("message", {})
                    text = msg.get("text", "")
                    if text == "/status":
                        status_report = "📊 **Current Status Report**\n\n"
                        for sym, bot in bots.items(): status_report += bot.get_detailed_status()
                        notifier.send_message(status_report)
                    elif text == "/check":
                        check_report = "🔍 **WebSocket Connectivity Check**\n\n"
                        now = time.time()
                        for sym, bot in bots.items():
                            last_seen = getattr(bot, 'last_ws_msg_ts', 0)
                            diff = now - last_seen if last_seen > 0 else 999999
                            status = "✅ Active" if diff < 30 else f"❌ SILENT ({int(diff)}s)"
                            check_report += f"• {sym}: {status}\n"
                        notifier.send_message(check_report)
                    elif text == "/close_all":
                        notifier.send_message("⚠️ **EMERGENCY: Closing all positions!**")
                        await asyncio.gather(*[bot.force_exit() for bot in bots.values()])
                        notifier.send_message("✅ All positions liquidated. Stopping bots."); os._exit(0)
                    elif text.startswith("/sniper_on"):
                        sym = text.split(" ")[1] if len(text.split(" ")) > 1 else None
                        if sym in bots: bots[sym].use_sniper = bots[sym].settings["USE_SNIPER"] = True; notifier.send_message(f"🎯 Sniper ENABLED for {sym}")
                    elif text.startswith("/sniper_off"):
                        sym = text.split(" ")[1] if len(text.split(" ")) > 1 else None
                        if sym in bots: bots[sym].use_sniper = bots[sym].settings["USE_SNIPER"] = False; await bots[sym].cancel_sniper_ambush(); notifier.send_message(f"🚫 Sniper DISABLED for {sym}")
                    elif text.startswith("/optimize"):
                        sym = text.split(" ")[1] if len(text.split(" ")) > 1 else None
                        if sym in bots:
                            notifier.send_message(f"⚙️ Optimizing {sym}..."); best_params = OptimizerEngine().optimize_symbol(sym)
                            if best_params: bots[sym].hot_reload_settings(best_params); notifier.send_message(f"✅ Optimized {sym}!\nNew Params: {best_params}")
        except Exception as e: logger.error(f"Error in handle_commands: {e}")
        await asyncio.sleep(2)

async def main():
    db, notifier = DBManager(), TelegramNotifier()
    exchange = getattr(ccxt, CONFIG["EXCHANGE"])({'apiKey': CONFIG["BINANCE_API_KEY"], 'secret': CONFIG["BINANCE_SECRET"], 'options': {'defaultType': 'future'}})
    pm = PortfolioManagerAsync(exchange, CONFIG)
    try:
        await exchange.load_markets()
        bots = {symbol: SymbolBotAsync(symbol, exchange, pm, notifier, db) for symbol in CONFIG["SYMBOLS_LIST"]}
        for bot in bots.values(): await bot.initialize()
        ws_manager = BinanceWebSocketManager(CONFIG["SYMBOLS_LIST"], api_key=CONFIG["BINANCE_API_KEY"], api_secret=CONFIG["BINANCE_SECRET"])
        async def ws_loop():
            msg_count = 0
            last_msg_log = time.time()

            async def process_msg(payload):
                try:
                    e_type = payload.get('e')
                    raw_symbol = payload.get('s') if 's' in payload else (payload['o']['s'] if 'o' in payload else None)
                    if not raw_symbol: return
                    
                    symbol = None
                    if raw_symbol in bots: 
                        symbol = raw_symbol
                    else:
                        for quote in ["USDT", "USDC"]:
                            if raw_symbol.endswith(quote):
                                test_sym = raw_symbol.replace(quote, f"/{quote}")
                                if test_sym in bots:
                                    symbol = test_sym
                                    break
                    
                    if symbol:
                        bots[symbol].last_ws_msg_ts = time.time()
                        if e_type == 'kline': await bots[symbol].on_kline_update(payload['k']['i'], payload['k'])
                        elif e_type == 'markPriceUpdate': await bots[symbol].on_mark_price_update(float(payload['p']))
                        elif e_type == 'ORDER_TRADE_UPDATE': await bots[symbol].on_order_update(payload['o'])
                except Exception as e:
                    logger.error(f"Error processing symbol event: {e}")

            async for msg in ws_manager.stream():
                try:
                    msg_count += 1
                    now = time.time()
                    if now - last_msg_log > 60:
                        logger.info(f"📡 WS Heartbeat: Received {msg_count} messages in last 60s")
                        msg_count = 0
                        last_msg_log = now

                    if isinstance(msg, dict) and msg.get('e') == 'WS_RECONNECTED':
                        logger.info("🔄 WS Reconnected. Triggering full order sync for all bots...")
                        for bot in bots.values(): asyncio.create_task(bot.sync_all_orders())
                        continue

                    payload = msg.get('data', msg) if isinstance(msg, dict) else msg
                    # Offload symbol processing to a separate task to avoid blocking the WS loop
                    asyncio.create_task(process_msg(payload))
                except Exception as e: logger.error(f"Error in ws_loop: {e}")
        logger.info(f"🚀 TrendCrusher {CONFIG['VERSION']} Async Core Started.")
        await asyncio.gather(ws_loop(), handle_commands(bots, notifier, pm))
    except Exception as e: logger.error(f"Fatal crash: {e}"); notifier.send_message(f"🚨 **CRITICAL BOT CRASH**: {e}")
    finally: await exchange.close(); logger.info("📡 Exchange connection closed.")

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as fatal_e: print(f"Final Fallback: {fatal_e}")
