import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import logging
import signal
import time
from datetime import datetime
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
        
        self.ohlcv_1h = None
        self.ohlcv_4h = None
        self.last_price = 0
        self.df_indicators = None
        
        # Throttling & Sync states
        self.last_db_record_ts = 0
        self.last_indicator_calc_ts = 0
        self.last_sl_sync_price = 0

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
                await self.retry_api_call(self.exchange.cancel_order, self.active_retest_order_id, self.symbol)
            self.logger.info(f"🎣 Retest order {self.active_retest_order_id} cancelled.")
        except Exception as e:
            self.logger.warning(f"Failed to cancel retest order for {self.symbol}: {e}")
        finally:
            self.active_retest_order_id = None
            self.retest_order_ts = None

    async def cancel_sniper_ambush(self):
        if not self.active_sniper_order_id: return
        try:
            await self.retry_api_call(self.exchange.cancel_order, self.active_sniper_order_id, self.symbol)
            self.logger.info(f"♻️ Sniper Cancelled for {self.symbol}")
        except ccxt.OrderNotFound: pass
        except Exception as e: self.logger.warning(f"Sniper cancel error: {e}")
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

            # EMA 200 안정을 위해 최소 500개 이상의 데이터를 가져옴
            self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"], limit=500)
            self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"], limit=500)
            self._update_indicators()
            self.logger.info(f"📊 Indicators Initialized (500 bars)")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize {self.symbol}: {e}")
            raise e

    def _update_indicators(self, is_live=False):
        if self.ohlcv_1h is not None and self.ohlcv_4h is not None:
            # 실시간 업데이트 시(is_live=True)는 엔진에서 최근 데이터만 슬라이싱하여 고속 계산
            self.df_indicators = self.engine.calculate_indicators(self.ohlcv_1h, self.ohlcv_4h, self.settings, is_live=is_live)

    async def on_kline_update(self, tf, kline):
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
            
            # Throttled Re-calculation (Every 10s or on candle close)
            now = time.time()
            if kline['x'] or (now - self.last_indicator_calc_ts > 10):
                self._update_indicators(is_live=True)
                self.last_indicator_calc_ts = now

            if not kline['x']:
                if self.position != 0: await self.check_exit()
                else: await self.check_entry()
        except Exception as e:
            self.logger.error(f"⚠️ Error updating OHLCV buffer for {self.symbol}: {e}")

    async def on_order_update(self, order_data):
        """
        Handles real-time order execution reports from User Data Stream.
        """
        try:
            order_id = order_data['i']
            symbol = order_data['s']
            status = order_data['X']
            side = order_data['S'].lower()
            qty = float(order_data['z']) # Cumulative filled quantity
            # Binance WS 'ap' field is the average price, more accurate for STOP_MARKET/MARKET fills
            avg_price = float(order_data.get('ap', order_data['L'])) 
            
            # [Diagnostic Log] Record every order update for transparency
            self.logger.info(f"📝 WS Order Update: {symbol} {side} {status} (ID: {order_id}, Qty: {qty}, Price: {avg_price:,.2f})")
            
            if status == 'FILLED':
                # 1. Sniper/Retest Entry Fill
                if order_id in [self.active_sniper_order_id, self.active_retest_order_id]:
                    self.logger.info(f"🎯 Ambush FILLED via WS: {symbol} {side} at {avg_price:,.2f}")
                    self.quantity = qty
                    self.entry_price = avg_price
                    direction = 1 if side == 'buy' else -1
                    await self._on_fill_success(direction)
                    self.active_sniper_order_id = None
                    self.active_retest_order_id = None
                    self.retest_order_ts = None
                
                # 2. Stop Loss Fill (Exit)
                elif order_id == self.sl_order_id:
                    self.logger.info(f"🛡️ StopLoss FILLED via WS: {symbol} {side} at {avg_price}")
                    pnl_pct = ((avg_price / self.entry_price) - 1) * 100 * self.position
                    pnl_usdt = (avg_price - self.entry_price) * qty * self.position
                    
                    self.db.log_trade_close(self.symbol, avg_price, pnl_pct, pnl_usdt)
                    await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
                    
                    self.position, self.sl_order_id = 0, None
                    self.persist_state()
                    self.notifier.notify_exit(f"SL {self.symbol}", avg_price, pnl_pct, pnl_usdt)
            
            elif status == 'CANCELED':
                if order_id == self.sl_order_id:
                    self.logger.warning(f"⚠️ SL Order {order_id} was CANCELED externally!")
                    self.sl_order_id = None
                elif order_id == self.active_sniper_order_id:
                    self.active_sniper_order_id = None
                    self.persist_state()
                elif order_id == self.active_retest_order_id:
                    self.active_retest_order_id = None
                    self.persist_state()

        except Exception as e:
            self.logger.error(f"Error in on_order_update: {e}")

    async def _record_live_status(self):
        if self.df_indicators is None or self.df_indicators.empty: return
        try:
            row = self.df_indicators.iloc[-1]
            last_price = self.last_price
            
            # 1. Volume Proximity (Current 1m sum vs Target)
            vol_target = row['avg_vol'] * self.settings.get('VOL_MULTIPLIER', 2.0)
            vol_ratio = min(1.0, row['volume'] / vol_target) if vol_target > 0 else 0
            
            # 2. ADX Proximity
            adx_target = self.settings.get('ADX_FILTER_LEVEL', 25.0)
            adx_ratio = min(1.0, row['adx'] / adx_target) if adx_target > 0 else 0
            
            # 3. Price Proximity to Breakout
            upper, lower = row['upper'], row['lower']
            ema = row['ema_h']
            prox_pct = self.settings.get('SNIPER_PROXIMITY_PCT', 0.005)
            
            trend_ok = False
            prox_ratio = 0
            
            if last_price > ema: # Long Bias
                trend_ok = True
                dist = abs(upper - last_price)
                prox_limit = upper * prox_pct
                prox_ratio = max(0, 1.0 - (dist / prox_limit)) if prox_limit > 0 else 0
            elif last_price < ema: # Short Bias
                trend_ok = True
                dist = abs(lower - last_price)
                prox_limit = lower * prox_pct
                prox_ratio = max(0, 1.0 - (dist / prox_limit)) if prox_limit > 0 else 0
                
            # Cap prox_ratio at 1.0 if already breakout
            if (last_price >= upper and trend_ok) or (last_price <= lower and trend_ok):
                prox_ratio = 1.0
                
            # 4. Total Signal Score (0-100)
            score = (prox_ratio * 40) + (vol_ratio * 30) + (adx_ratio * 30)
            if not trend_ok: score *= 0.5 # Penalty for wrong trend
            
            self.db.update_live_status(
                self.symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, score,
                last_price, upper, lower, float(row['adx'])
            )
        except Exception as e:
            self.logger.error(f"Error recording live status: {e}")

    async def _on_fill_success(self, direction):
        side_str = "LONG" if direction == 1 else "SHORT"
        try:
            if not self.settings["DRY_RUN"]:
                params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
                self.sl_order_id = sl_order['id']
            else:
                self.sl_order_id = "DRY_SL"
        except Exception as sl_err:
            self.logger.error(f"🚨 CRITICAL: SL failed: {sl_err}. EMERGENCY LIQUIDATION!")
            if not self.settings["DRY_RUN"]:
                await self.exchange.create_market_order(self.symbol, 'sell' if direction == 1 else 'buy', self.quantity)
            return
        self.position = direction
        self.max_price_seen = self.entry_price
        self.min_price_seen = self.entry_price
        self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
        self.persist_state()
        self.notifier.notify_entry(f"🚀 {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)

    async def check_sniper_fill(self):
        """Fallback check for sniper fill (Polled). Preferred is via on_order_update."""
        if self.settings["DRY_RUN"] or not self.active_sniper_order_id: return
        try:
            order = await self.retry_api_call(self.exchange.fetch_order, self.active_sniper_order_id, self.symbol)
            if order and isinstance(order, dict) and order.get('status') == 'closed':
                self.logger.info(f"🎯 Sniper Order FILLED for {self.symbol} (Polled)!")
                self.quantity = float(order.get('filled') or order.get('amount') or self.quantity)
                self.entry_price = float(order.get('average') or order.get('price') or self.entry_price)
                direction = 1 if order.get('side') == 'buy' else -1
                await self._on_fill_success(direction)
                self.active_sniper_order_id = None
                self.persist_state()
        except Exception as e:
            self.logger.error(f"Error checking sniper fill: {e}")

    async def check_retest_fill(self):
        """Fallback check for retest fill (Polled). Preferred is via on_order_update."""
        if not self.active_retest_order_id: return
        if self.retest_order_ts:
            elapsed = (datetime.now() - self.retest_order_ts).total_seconds()
            if elapsed > 14400:
                self.logger.info(f"⌛ Retest order TIMEOUT (4h) for {self.symbol}. Cancelling.")
                await self.cancel_retest_order()
                return
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
        except Exception as e:
            self.logger.error(f"Error checking retest fill: {e}")

    async def check_entry(self):
        if self.is_halted or self.df_indicators is None: return
        row = self.df_indicators.iloc[-1]
        
        # Determine if we already have an active ambush order
        is_ambushing = bool(self.active_sniper_order_id or self.active_retest_order_id)
        
        sig_type, target_p, sl_p = self.engine.check_entry_signal(
            row, self.last_price, self.use_sniper, self.use_retest_maker, self.settings, 
            is_ambushing=is_ambushing
        )
        
        if sig_type is None:
            if self.active_sniper_order_id:
                self.logger.info(f"🚫 Sniper weakened. Aborting {self.symbol}."); await self.cancel_sniper_ambush()
            if self.active_retest_order_id:
                self.logger.info(f"🚫 Retest conditions weakened. Aborting {self.symbol}."); await self.cancel_retest_order()
            return

        if self.active_retest_order_id: return 

        if sig_type == 'RETEST':
            direction = 1 if target_p > row['ema_h'] else -1
            await self.manage_retest_ambush(direction, target_p, sl_p)
        elif sig_type == 'SNIPER':
            direction = 1 if target_p > row['ema_h'] else -1
            atr = row['atr']
            await self.manage_sniper_ambush(direction, target_p, atr)
        elif sig_type == 'MARKET':
            direction = 1 if target_p > row['ema_h'] else -1
            await self.execute_entry(direction, row['atr'])

    async def on_mark_price_update(self, price):
        self.last_price = price
        
        now = time.time()
        # Throttled DB/Dashboard update (Every 5 seconds)
        if now - self.last_db_record_ts > 5:
            await self._record_live_status()
            self.last_db_record_ts = now
            
        # [NEW] Throttled Fill Check Polling (Every 30 seconds)
        if now - getattr(self, "last_fill_poll_ts", 0) > 30:
            if self.active_sniper_order_id: await self.check_sniper_fill()
            if self.active_retest_order_id: await self.check_retest_fill()
            self.last_fill_poll_ts = now
        
        if self.position != 0:
            await self.check_exit()
        else:
            # Note: Sniper/Retest fills are now handled via on_order_update (WebSocket)
            # We only use mark price for manual checks if DRY_RUN is enabled
            if self.settings["DRY_RUN"]:
                if self.active_retest_order_id:
                    is_filled = False
                    if self.entry_price > 0 and price <= self.entry_price: is_filled = True
                    elif self.entry_price < 0 and price >= abs(self.entry_price): is_filled = True
                    if is_filled:
                        self.logger.info(f"🧪 [DRY RUN] Retest Maker FILLED at {price}")
                        direction = 1 if self.entry_price > 0 else -1
                        self.entry_price = abs(self.entry_price)
                        await self._on_fill_success(direction)
                        self.active_retest_order_id = None
                # Sniper dry run fill could be added here similarly
            await self.check_entry()

    async def check_exit(self):
        if self.df_indicators is None or self.position == 0: return
        row = self.df_indicators.iloc[-1]
        
        # Adaptive Trailing logic is inside engine.check_exit_signal
        old_sl = self.sl_price
        
        state = {
            'position': self.position,
            'entry_price': self.entry_price,
            'max_price_seen': self.max_price_seen,
            'min_price_seen': self.min_price_seen,
            'sl_price': self.sl_price
        }
        
        if self.engine.check_exit_signal(row, self.last_price, state, self.settings):
            self.logger.info(f"📉 Exit Signal Triggered for {self.symbol} at {self.last_price}")
            await self.execute_exit()
        else:
            # Sync SL update from engine back to bot
            self.sl_price = state['sl_price']
            
            # 1. Update extremes
            if self.position == 1: self.max_price_seen = max(self.max_price_seen, self.last_price)
            else: self.min_price_seen = min(self.min_price_seen, self.last_price)
            
            # 2. Sync SL to Exchange if moved significantly (> 0.05% change to avoid spam)
            if abs(self.sl_price - self.last_sl_sync_price) / (self.last_sl_sync_price or 1) > 0.0005:
                await self.sync_sl_to_exchange()

    async def sync_sl_to_exchange(self):
        """Updates the actual STOP_MARKET order on the exchange."""
        if self.settings["DRY_RUN"] or not self.sl_order_id: return
        
        try:
            self.logger.info(f"🔄 Syncing SL for {self.symbol} -> {self.sl_price:,.2f}")
            try:
                await self.retry_api_call(self.exchange.cancel_order, self.sl_order_id, self.symbol)
            except Exception as e:
                self.logger.warning(f"Could not cancel old SL {self.sl_order_id} during sync: {e}")
            
            params = {'stopPrice': self.sl_price, 'reduceOnly': True}
            side = 'sell' if self.position == 1 else 'buy'
            sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', side, self.quantity, None, params)
            self.sl_order_id = sl_order['id']
            self.last_sl_sync_price = self.sl_price
            self.persist_state()
        except Exception as e:
            self.logger.error(f"❌ SL Sync Failed for {self.symbol}: {e}")

    async def execute_entry(self, direction, atr):
        side_str = "LONG" if direction == 1 else "SHORT"
        self.sl_price = float(self.last_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else self.last_price + (atr * self.settings["INITIAL_SL_ATR"]))
        
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if qty is None or qty <= 0:
            self.logger.warning(f"🚫 Entry skipped: Invalid quantity ({qty}) for {self.symbol}"); return
        
        self.quantity = float(qty)
        
        try:
            if not self.settings["DRY_RUN"]:
                # [Margin Safety Guard]
                balance = await self.retry_api_call(self.exchange.fetch_balance)
                quote_currency = self.symbol.split('/')[-1]
                available_margin = float(balance.get(quote_currency, {}).get('free', 0))
                leverage = self.settings.get("MAX_LEVERAGE", 1)
                required_margin = (self.quantity * self.last_price) / leverage
                
                if required_margin > available_margin * 0.95:
                    old_qty = self.quantity
                    self.quantity = (available_margin * 0.95 * leverage) / self.last_price
                    self.quantity = float(self.exchange.amount_to_precision(self.symbol, self.quantity))
                    self.logger.warning(f"⚠️ Margin Guard: Reduced Qty {old_qty} -> {self.quantity} (Avail: {available_margin:.2f} {quote_currency})")
                    if self.quantity <= 0: return

                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                if pos and float(pos['contracts']) != 0:
                    self.logger.warning(f"⚠️ Entry aborted: Position already exists for {self.symbol}. Aligning state.")
                    self.position = 1 if float(pos['contracts']) > 0 else -1
                    self.entry_price = float(pos['entryPrice'])
                    self.quantity = abs(float(pos['contracts']))
                    self.persist_state(); return

                side = 'buy' if direction == 1 else 'sell'
                order = await self.exchange.create_market_order(self.symbol, side, self.quantity)
                
                if order and isinstance(order, dict):
                    self.entry_price = float(order.get('average') or order.get('price') or self.last_price)
                    self.quantity = float(order.get('filled') or self.quantity)
                
                try: 
                    params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                    sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
                    self.sl_order_id = sl_order['id']
                except Exception as sl_err:
                    self.logger.error(f"🚨 CRITICAL SL FAILED: {sl_err}")
                    await self.exchange.create_market_order(self.symbol, 'sell' if direction == 1 else 'buy', self.quantity); return
            else:
                self.entry_price = self.last_price
            
            self.position = direction
            self.max_price_seen = self.min_price_seen = self.entry_price
            self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
            self.persist_state()
            self.notifier.notify_entry(f"Async {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)
        except Exception as e: 
            self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        if self.position == 0: return
        try:
            pnl_pct = 0
            pnl_usdt = 0
            exit_price = self.last_price
            
            if not self.settings["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                order = await self.exchange.create_market_order(self.symbol, side, self.quantity)
                
                await asyncio.sleep(1)
                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                if pos and float(pos['contracts']) != 0:
                    self.logger.warning(f"⚠️ Exit Verification: Partial exit detected. Trying remaining {pos['contracts']}")
                    await self.exchange.create_market_order(self.symbol, side, abs(float(pos['contracts'])))

                if order and isinstance(order, dict):
                    exit_price = float(order.get('average') or order.get('price') or self.last_price)
                
                try:
                    if self.sl_order_id: await self.retry_api_call(self.exchange.cancel_order, self.sl_order_id, self.symbol)
                except: pass
                
            pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
            pnl_usdt = (exit_price - self.entry_price) * self.quantity * self.position
            
            self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
            await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
            
            self.logger.info(f"✅ Trade Closed: {self.symbol} at {exit_price:,.2f} ({pnl_pct:+.2f}%)")
            self.notifier.notify_exit(f"Async {self.symbol}", exit_price, pnl_pct, pnl_usdt)
            
            self.position = 0
            self.entry_price = 0
            self.quantity = 0
            self.sl_order_id = None
            self.persist_state()
        except Exception as e:
            self.logger.error(f"Exit error: {e}")

    async def force_exit(self):
        try:
            self.logger.info(f"🚨 FORCE EXIT Triggered for {self.symbol}")
            positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
            pos = next((p for p in positions if p['symbol'] == self.symbol), None)
            
            exit_price = self.last_price
            if pos and float(pos['contracts']) != 0:
                side = 'sell' if float(pos['contracts']) > 0 else 'buy'
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, abs(float(pos['contracts'])))
                if order and isinstance(order, dict):
                    exit_price = float(order.get('average') or order.get('price') or exit_price)
                self.logger.info(f"✅ Market liquidation order sent for {self.symbol}")

            await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol)

            # Record trade close if we had an active position in memory or exchange
            if self.position != 0:
                pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
                pnl_usdt = (exit_price - self.entry_price) * self.quantity * self.position
                self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
                await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)

            self.position = 0
            self.entry_price = 0
            self.quantity = 0
            self.sl_order_id = None
            self.persist_state()
        except Exception as e:
            self.logger.error(f"❌ Force exit failed for {self.symbol}: {e}")

    def persist_state(self):
        try:
            self.db.save_bot_state(
                self.symbol, self.position, self.entry_price, self.quantity, 
                self.max_price_seen, self.min_price_seen, self.sl_price, self.sl_order_id,
                self.active_sniper_order_id, self.active_retest_order_id
            )
        except Exception as e:
            self.logger.error(f"Failed to persist state: {e}")

async def handle_commands(bots, notifier, pm):
    from src.optimizer_engine import OptimizerEngine
    offset = None
    try:
        initial_updates = notifier.get_updates(offset)
        if initial_updates and initial_updates.get("ok") and initial_updates.get("result"):
            offset = initial_updates["result"][-1]["update_id"] + 1
            logger.info(f"🧹 Flushed {len(initial_updates['result'])} old commands.")
    except: pass

    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    
                    if text == "/status":
                        status_report = "📊 **Current Status Report**\n\n"
                        for sym, bot in bots.items():
                            pnl_str = ""
                            if bot.position != 0:
                                pnl = ((bot.last_price / bot.entry_price) - 1) * 100 * bot.position
                                pnl_str = f" | PnL: {pnl:+.2f}%"
                            
                            ambush = ""
                            if bot.active_sniper_order_id: ambush = " (🎯 Sniper Active)"
                            elif bot.active_retest_order_id: ambush = " (🎣 Retest Active)"
                            
                            status_report += f"• **{sym}**: {bot.position}{pnl_str}{ambush}\n"
                        notifier.send_message(status_report)
                    
                    elif text == "/close_all":
                        notifier.send_message("⚠️ **EMERGENCY: Closing all positions!**")
                        await asyncio.gather(*[bot.force_exit() for bot in bots.values()])
                        notifier.send_message("✅ All positions liquidated. Stopping bots.")
                        os._exit(0)
                        
                    elif text.startswith("/sniper_on"):
                        sym = text.split(" ")[1] if len(text.split(" ")) > 1 else None
                        if sym in bots:
                            bots[sym].use_sniper = True
                            bots[sym].settings["USE_SNIPER"] = True
                            notifier.send_message(f"🎯 Sniper mode **ENABLED** for {sym}")
                        else: notifier.send_message("Please specify a valid symbol, e.g. /sniper_on BTC/USDT")

                    elif text.startswith("/sniper_off"):
                        sym = text.split(" ")[1] if len(text.split(" ")) > 1 else None
                        if sym in bots:
                            bots[sym].use_sniper = False
                            bots[sym].settings["USE_SNIPER"] = False
                            await bots[sym].cancel_sniper_ambush()
                            notifier.send_message(f"🚫 Sniper mode **DISABLED** for {sym}")
                        else: notifier.send_message("Please specify a valid symbol, e.g. /sniper_off BTC/USDT")

                    elif text.startswith("/optimize"):
                        sym = text.split(" ")[1] if len(text.split(" ")) > 1 else None
                        if sym in bots:
                            notifier.send_message(f"⚙️ Starting optimization for **{sym}**... (This may take a minute)")
                            engine = OptimizerEngine()
                            best_params = engine.optimize_symbol(sym)
                            if best_params:
                                bots[sym].hot_reload_settings(best_params)
                                notifier.send_message(f"✅ Optimization complete for {sym}!\nNew Params: {best_params}")
                        else: notifier.send_message("Please specify a valid symbol, e.g. /optimize BTC/USDT")

        except Exception as e: logger.error(f"Error in handle_commands: {e}")
        await asyncio.sleep(2)

async def main():
    db = DBManager()
    notifier = TelegramNotifier()
    
    exchange_class = getattr(ccxt, CONFIG["EXCHANGE"])
    exchange = exchange_class({
        'apiKey': CONFIG["BINANCE_API_KEY"],
        'secret': CONFIG["BINANCE_SECRET"],
        'options': {'defaultType': 'future'}
    })
    
    pm = PortfolioManagerAsync(exchange, CONFIG)

    try:
        await exchange.load_markets()
        bots = {}
        for symbol in CONFIG["SYMBOLS_LIST"]:
            bot = SymbolBotAsync(symbol, exchange, pm, notifier, db)
            await bot.initialize()
            bots[symbol] = bot

        ws_manager = BinanceWebSocketManager(CONFIG["SYMBOLS_LIST"], exchange)
        
        async def ws_loop():
            async for msg in ws_manager.stream():
                if msg['e'] == 'kline':
                    symbol = msg['s'].replace("USDT", "/USDT") # Simplistic mapping
                    if symbol in bots:
                        await bots[symbol].on_kline_update(msg['k']['i'], msg['k'])
                elif msg['e'] == 'ORDER_TRADE_UPDATE':
                    symbol = msg['o']['s'].replace("USDT", "/USDT")
                    if symbol in bots:
                        await bots[symbol].on_order_update(msg['o'])

        logger.info(f"🚀 TrendCrusher {CONFIG['VERSION']} Async Core Started.")
        await asyncio.gather(ws_loop(), handle_commands(bots, notifier, pm))

    except Exception as e:
        logger.error(f"Fatal crash in main: {e}")
        notifier.send_message(f"🚨 **CRITICAL BOT CRASH**: {e}")
    finally:
        await exchange.close()
        logger.info("📡 Exchange connection closed.")

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as fatal_e: print(f"Final Fallback: {fatal_e}")
