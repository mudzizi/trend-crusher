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

                self.logger.info(f"🏹 Sniper: {side.upper()} LIMIT at {target_price:,.2f}")
                order = await self.retry_api_call(self.exchange.create_limit_order, self.symbol, side, self.quantity, target_price)
                self.active_sniper_order_id = order['id']
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
                self.logger.info(f"💾 Recovered: Pos={self.position}, Entry={self.entry_price}")

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
            avg_price = float(order_data['L']) # Last filled price (or use 'ap' for average)
            
            if status == 'FILLED':
                # 1. Sniper/Retest Entry Fill
                if order_id in [self.active_sniper_order_id, self.active_retest_order_id]:
                    self.logger.info(f"🎯 Ambush FILLED via WS: {symbol} {side} at {avg_price}")
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
                elif order_id == self.active_retest_order_id:
                    self.active_retest_order_id = None

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
        
        # Throttled DB/Dashboard update (Every 5 seconds)
        now = time.time()
        if now - self.last_db_record_ts > 5:
            await self._record_live_status()
            self.last_db_record_ts = now
        
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
        # We need to capture if SL moved
        old_sl = self.sl_price
        
        state = {
            'position': self.position,
            'entry_price': self.entry_price,
            'max_price_seen': self.max_price_seen,
            'min_price_seen': self.min_price_seen,
            'sl_price': self.sl_price
        }
        
        # check_exit_signal might update state['sl_price'] if it's trailing
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
            # Binance Futures allows editing stopPrice of an existing order
            # but CCXT's edit_order support varies. Safe approach: Cancel and Replace.
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
        
        # 1. 전략 기반 수량 계산 (기존 로직 유지)
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if qty is None or qty <= 0:
            self.logger.warning(f"🚫 Entry skipped: Invalid quantity ({qty}) for {self.symbol}"); return
        
        self.quantity = float(qty)
        
        try:
            if not self.settings["DRY_RUN"]:
                # 2. [Margin Safety Guard] 실시간 가용 증거금 확인
                balance = await self.retry_api_call(self.exchange.fetch_balance)
                
                # 심볼에서 정산 통화(USDT 또는 USDC) 추출 (예: BTC/USDT -> USDT)
                quote_currency = self.symbol.split('/')[-1]
                available_margin = float(balance.get(quote_currency, {}).get('free', 0))
                
                # 필요 증거금 계산 (수량 * 가격 / 레버리지)
                leverage = self.settings.get("MAX_LEVERAGE", 1)
                required_margin = (self.quantity * self.last_price) / leverage
                
                # 안전 계수(0.95) 적용: 수수료 및 가격 변동 대비
                if required_margin > available_margin * 0.95:
                    old_qty = self.quantity
                    self.quantity = (available_margin * 0.95 * leverage) / self.last_price
                    # 거래소별 최소 주문 수량 단위(Step Size)에 맞게 버림 처리 필요
                    self.quantity = float(self.exchange.amount_to_precision(self.symbol, self.quantity))
                    
                    self.logger.warning(f"⚠️ Margin Guard: Reduced Qty {old_qty} -> {self.quantity} (Avail: {available_margin:.2f} {quote_currency})")
                    if self.quantity <= 0:
                        self.logger.error(f"🚫 Entry aborted: Insufficient {quote_currency} available margin.")
                        return

                # 3. 중복 진입 방지 확인
                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                if pos and float(pos['contracts']) != 0:
                    self.logger.warning(f"⚠️ Entry aborted: Position already exists for {self.symbol}. Aligning state.")
                    self.position = 1 if float(pos['contracts']) > 0 else -1
                    self.entry_price = float(pos['entryPrice'])
                    self.quantity = abs(float(pos['contracts']))
                    self.persist_state(); return

                side = 'buy' if direction == 1 else 'sell'
                # 2. Execute Entry (Without automatic retry to prevent double spending)
                order = await self.exchange.create_market_order(self.symbol, side, self.quantity)
                
                # IMPORTANT: Use actual exchange-reported fill price and quantity
                if order and isinstance(order, dict):
                    self.entry_price = float(order.get('average') or order.get('price') or self.last_price)
                    self.quantity = float(order.get('filled') or self.quantity)
                else:
                    self.logger.error(f"⚠️ Exchange returned invalid order response for {self.symbol} during entry. Using fallback.")
                    self.entry_price = self.last_price
                
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
            # On error, don't retry immediately, let the next tick handle it by checking position again

    async def execute_exit(self):
        # Guard against ZeroDivision or invalid state
        if self.position == 0: return
        
        try:
            pnl_pct = 0
            pnl_usdt = 0
            exit_price = self.last_price
            
            if not self.settings["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                # 1. Execute Market Order (No automatic retry here)
                order = await self.exchange.create_market_order(self.symbol, side, self.quantity)
                
                # 2. VERIFY: Did the position actually close on the exchange?
                await asyncio.sleep(1)
                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                
                if pos and float(pos['contracts']) != 0:
                    self.logger.error(f"🚨 EXIT FAILED: Position still exists for {self.symbol} ({pos['contracts']} left).")
                    return # Don't clear state, try again next tick

                if order and isinstance(order, dict):
                    exit_price = float(order.get('average') or order.get('price') or self.last_price)
                    filled_qty = float(order.get('filled') or self.quantity)
                    # Safe nested access for fee
                    order_fee = order.get('fee')
                    if order_fee and isinstance(order_fee, dict):
                        fee = order_fee.get('cost', exit_price * filled_qty * 0.0005)
                    else:
                        fee = exit_price * filled_qty * 0.0005
                else:
                    self.logger.warning(f"⚠️ Exit order response is None or invalid for {self.symbol}. Using fallback data.")
                    exit_price = self.last_price
                    filled_qty = self.quantity
                    fee = exit_price * filled_qty * 0.0005
                
                pnl_usdt = (exit_price - self.entry_price) * filled_qty * self.position
                pnl_usdt -= float(fee)
                
                # 3. Safe SL Cancellation
                if self.sl_order_id:
                    try: 
                        # Check status before cancelling to avoid error if already filled
                        sl_status = await self.exchange.fetch_order(self.sl_order_id, self.symbol)
                        if sl_status['status'] == 'open':
                            await self.exchange.cancel_order(self.sl_order_id, self.symbol)
                    except Exception as e:
                        self.logger.warning(f"Could not cancel SL {self.sl_order_id}: {e}")
            else:
                pnl_usdt = (exit_price - self.entry_price) * self.quantity * self.position
            
            if self.entry_price > 0:
                pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
            
            self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
            await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
            new_total_equity = await self.pm.get_total_equity()
            self.db.log_equity(new_total_equity, 'TOTAL')
            
            self.position, self.sl_order_id = 0, None
            self.persist_state()
            self.notifier.notify_exit(f"Async {self.symbol}", exit_price, pnl_pct, pnl_usdt)
        except Exception as e: 
            self.logger.error(f"Exit error: {e}")

    async def force_exit(self):
        """
        Hyper-safe exit that checks actual exchange positions to close them.
        """
        try:
            if self.settings["DRY_RUN"]:
                self.position = 0
                self.persist_state()
                return

            # 1. Fetch real position from exchange to ensure closure
            positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
            pos = next((p for p in positions if p['symbol'] == self.symbol), None)
            
            if pos and float(pos['contracts']) != 0:
                side = 'sell' if float(pos['contracts']) > 0 else 'buy'
                qty = abs(float(pos['contracts']))
                self.logger.info(f"🆘 Force closing {qty} {self.symbol} ({side})")
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, qty)
                
                if order and isinstance(order, dict):
                    exit_price = float(order.get('average') or order.get('price') or self.last_price)
                    filled_qty = float(order.get('filled') or qty)
                    # Safe nested access for fee
                    order_fee = order.get('fee')
                    if order_fee and isinstance(order_fee, dict):
                        fee = order_fee.get('cost', exit_price * filled_qty * 0.0005)
                    else:
                        fee = exit_price * filled_qty * 0.0005
                else:
                    self.logger.error(f"⚠️ Exchange returned invalid order response for {self.symbol} during force exit.")
                    exit_price = self.last_price
                    filled_qty = qty
                    fee = exit_price * filled_qty * 0.0005
                
                pnl_usdt = (exit_price - self.entry_price) * filled_qty * self.position
                pnl_usdt -= float(fee)
                
                pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
                self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
                await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
                
                new_total_equity = await self.pm.get_total_equity()
                self.db.log_equity(new_total_equity, 'TOTAL')
                
            # 2. Cancel all open orders for this symbol
            await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol)
            
            # 3. Reset internal state
            self.position = 0
            self.persist_state()
        except Exception as e:
            self.logger.error(f"❌ Force exit failed for {self.symbol}: {e}")

    def persist_state(self):
        self.db.save_bot_state(self.symbol, self.position, self.entry_price, self.quantity, self.max_price_seen, self.min_price_seen, self.sl_price, self.sl_order_id)

async def handle_commands(bots, notifier, pm):
    from src.optimizer_engine import OptimizerEngine
    offset = None
    try:
        initial_updates = notifier.get_updates(offset)
        if initial_updates and initial_updates.get("ok") and initial_updates.get("result"):
            offset = initial_updates["result"][-1]["update_id"] + 1
            logger.info(f"🧹 Flushed {len(initial_updates['result'])} old commands.")
    except: pass
    optimizer = OptimizerEngine(config=CONFIG)
    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for result in updates.get("result", []):
                    offset = result["update_id"] + 1
                    msg = result.get("message", {})
                    text, chat_id = msg.get("text", ""), str(msg.get("chat", {}).get("id", ""))
                    if chat_id != str(CONFIG["TELEGRAM_CHAT_ID"]): continue
                    parts = text.split()
                    if not parts: continue
                    cmd = parts[0].lower()
                    if cmd == "/status": await send_summary(bots, notifier, pm)
                    elif cmd == "/sync":
                        notifier.notify_status("🔄 Manual synchronization started...")
                        changed = await sync_db_with_exchange(bots, bots[list(bots.keys())[0]].exchange, db, pm, notifier)
                        if not changed: notifier.notify_status("✅ No discrepancies found. All states are synchronized.")
                    elif cmd == "/retest_on":

                        target = parts[1].upper() if len(parts) > 1 else None
                        if target:
                            key = target.replace('/', '').lower()
                            if key in bots: 
                                bots[key].use_retest_maker = True
                                if bots[key].active_sniper_order_id: await bots[key].cancel_sniper_ambush()
                                notifier.notify_status(f"🎣 Retest Maker ENABLED for {target}.")
                            else: notifier.notify_error(f"Symbol {target} not found.")
                        else:
                            for b in bots.values(): 
                                b.use_retest_maker = True
                                if b.active_sniper_order_id: await b.cancel_sniper_ambush()
                            notifier.notify_status("🎣 Retest Maker ENABLED for ALL symbols.")
                    elif cmd == "/retest_off":
                        target = parts[1].upper() if len(parts) > 1 else None
                        if target:
                            key = target.replace('/', '').lower()
                            if key in bots: 
                                bots[key].use_retest_maker = False
                                if bots[key].active_retest_order_id: await bots[key].cancel_retest_order()
                                notifier.notify_status(f"🚫 Retest Maker DISABLED for {target}.")
                            else: notifier.notify_error(f"Symbol {target} not found.")
                        else:
                            for b in bots.values(): 
                                b.use_retest_maker = False
                                if b.active_retest_order_id: await b.cancel_retest_order()
                            notifier.notify_status("🚫 Retest Maker DISABLED for ALL symbols.")
                    elif cmd == "/sniper_on":
                        target = parts[1].upper() if len(parts) > 1 else None
                        if target:
                            key = target.replace('/', '').lower()
                            if key in bots: bots[key].use_sniper = True; notifier.notify_status(f"🎯 Sniper ENABLED for {target}.")
                            else: notifier.notify_error(f"Symbol {target} not found.")
                        else:
                            for b in bots.values(): b.use_sniper = True
                            notifier.notify_status("🎯 Sniper ENABLED for ALL symbols.")
                    elif cmd == "/sniper_off":
                        target = parts[1].upper() if len(parts) > 1 else None
                        if target:
                            key = target.replace('/', '').lower()
                            if key in bots: 
                                bots[key].use_sniper = False
                                if bots[key].active_sniper_order_id: await bots[key].cancel_sniper_ambush()
                                notifier.notify_status(f"🚫 Sniper DISABLED for {target}.")
                            else: notifier.notify_error(f"Symbol {target} not found.")
                        else:
                            for b in bots.values(): 
                                b.use_sniper = False
                                if b.active_sniper_order_id: await b.cancel_sniper_ambush()
                            notifier.notify_status("🚫 Sniper DISABLED for ALL symbols.")
                    elif cmd == "/stop":
                        for b in bots.values(): b.is_halted = True
                        notifier.notify_status("🛑 New entries HALTED.")
                    elif cmd == "/resume":
                        for b in bots.values(): b.is_halted = False
                        notifier.notify_status("▶️ New entries RESUMED.")
                    elif cmd == "/close_all":
                        notifier.notify_status("🆘 EMERGENCY SHUTDOWN: Force closing all positions and cancelling orders...")
                        tasks = []
                        for b in bots.values():
                            # Use force_exit to ensure actual exchange data cleanup
                            tasks.append(b.force_exit())
                        
                        if tasks:
                            await asyncio.gather(*tasks, return_exceptions=True)
                        
                        notifier.notify_status("🛑 ALL positions force-closed. Bot process terminating.")
                        await asyncio.sleep(2) 
                        os._exit(0)
                # Correctly end the for loop here
        except Exception as e:
            logger.error(f"Command processing error: {e}")
        await asyncio.sleep(1) # Increased responsiveness

async def auto_sentinel_loop(bots, notifier, pm):
    from src.optimizer_engine import OptimizerEngine
    optimizer = OptimizerEngine(config=CONFIG)
    while True:
        await asyncio.sleep(7 * 24 * 3600)
        notifier.notify_status("🛰️ Sentinel is performing weekly optimization scan.")
        for bot in bots.values():
            try:
                best = await optimizer.find_best_params(bot.symbol)
                if best:
                    bot.pending_settings = {"VOL_MULTIPLIER": best['vol_m'], "ADX_FILTER_LEVEL": best['adx_f'], "EMA_TREND_PERIOD": best['ema_p']}
                    notifier.send_report(f"🛰️ Sentinel Patrol Report: {bot.symbol}", {"New Vol": best['vol_m'], "New ADX": best['adx_f'], "New EMA": best['ema_p'], "Est. Return": f"{best['return']:.2f}%", "Est. MDD": f"{best['mdd']:.2f}%", "Action": f"/apply {bot.symbol}"})
                await asyncio.sleep(60)
            except Exception as e: logger.error(f"Sentinel Patrol Error: {e}")

async def auto_sync_loop(bots, exchange, db, pm, notifier):
    """Periodically syncs bot state with exchange every 1 hour."""
    while True:
        await asyncio.sleep(3600)
        await sync_db_with_exchange(bots, exchange, db, pm, notifier)

async def send_summary(bots, notifier, pm):
    report, active_count, total_value = {}, 0, 0
    for bot in bots.values():
        cap = await pm.get_total_equity(bot.symbol)
        total_value += cap
        status = "IDLE"
        if bot.position != 0:
            active_count += 1
            pnl = ((bot.last_price / bot.entry_price) - 1) * 100 * bot.position
            roe = pnl * pm.config.get("MAX_LEVERAGE", 1)
            status = f"{'LONG' if bot.position==1 else 'SHORT'} (Asset: {pnl:+.2f}% | ROE: {roe:+.2f}%)"
        elif bot.active_retest_order_id: status = "🎣 RETESTING"
        elif bot.active_sniper_order_id: status = "🎯 AMBUSHING"
        if bot.pending_settings: status += " 🧠(PENDING)"
        report[f"{bot.symbol} (${cap:,.0f})"] = status
    report["---"] = "---"
    report["Total Portfolio"] = f"${total_value:,.2f}"
    report["Active Positions"] = active_count
    first = next(iter(bots.values())) if bots else None
    report["Halted"] = first.is_halted if first else False
    report["Sniper/Retest"] = f"{'ON' if first and first.use_sniper else 'OFF'} / {'ON' if first and first.use_retest_maker else 'OFF'}"
    reply_markup = {"keyboard": [[{"text": "/status"}, {"text": "/sync"}, {"text": "/retest_on"}, {"text": "/retest_off"}], [{"text": "/sniper_on"}, {"text": "/sniper_off"}, {"text": "/stop"}], [{"text": "/resume"}, {"text": "/close_all"}]], "resize_keyboard": True}
    notifier.send_message(f"📋 *Portfolio Heartbeat (v{CONFIG['VERSION']})*\n\n" + "\n".join([f"• *{k}*: {v}" for k, v in report.items()]), reply_markup=reply_markup)

async def heartbeat_loop(bots, notifier, pm):
    count = 0
    while True:
        await asyncio.sleep(60)
        count += 1
        lev = pm.config.get("MAX_LEVERAGE", 1)
        for bot in bots.values():
            status = "IDLE"
            if bot.position != 0:
                pnl = ((bot.last_price / bot.entry_price) - 1) * 100 * bot.position
                status = f"{'LONG' if bot.position==1 else 'SHORT'} (Asset: {pnl:+.2f}% | ROE: {pnl*lev:+.2f}%)"
            elif bot.active_retest_order_id: status = "🎣 RETESTING"
            elif bot.active_sniper_order_id: status = "🎯 AMBUSHING"
            logger.info(f"💓 [{bot.symbol}] Price: {bot.last_price:,.2f} | Status: {status}")
        if count >= 60:
            await send_summary(bots, notifier, pm); count = 0

async def shutdown(sig, loop, notifier, exchange):
    logger.warning(f"Received exit signal {sig.name}...")
    try: notifier.notify_error(f"💀 *[TERMINATED]* Bot received {sig.name} and is shutting down.")
    except: pass
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await exchange.close(); loop.stop()
    logger.info("👋 Cleanup complete. Bot stopped.")

async def sync_db_with_exchange(bots, exchange, db, pm, notifier=None):
    """
    Robust synchronization: Aligns DB and Bot memory with actual exchange positions.
    Handles both 'Ghost Positions' (DB says open, Exchange says closed)
    and 'Missing Positions' (DB says closed, Exchange says open).
    """
    logger.info("🔍 [SYNC] Synchronizing DB/Bot state with actual exchange positions...")
    try:
        # 1. Fetch real positions from exchange
        all_positions = await exchange.fetch_positions()
        # Create a map for easy lookup: 'btcusdt' -> position_data
        real_pos_map = {p['symbol'].replace('/', '').lower(): p for p in all_positions if float(p['contracts']) != 0}

        report = []
        # 2. Iterate through all managed symbols
        for ws_key, bot in bots.items():
            sym = bot.symbol
            real_pos = real_pos_map.get(ws_key)
            
            # Case A: Exchange has position, but Bot thinks it's IDLE (Missing Position)
            if real_pos and bot.position == 0:
                side = 1 if float(real_pos['contracts']) > 0 else -1
                bot.position = side
                bot.entry_price = float(real_pos['entryPrice'])
                bot.quantity = abs(float(real_pos['contracts']))
                bot.max_price_seen = bot.entry_price
                bot.min_price_seen = bot.entry_price
                
                # Update DB and SL state
                db.log_trade_open(sym, "LONG" if side == 1 else "SHORT", bot.entry_price, bot.quantity, 100)
                bot.persist_state()
                msg = f"✅ [SYNC] Restored missing {sym} { 'LONG' if side==1 else 'SHORT' } position from exchange."
                logger.warning(msg); report.append(msg)

            # Case B: Exchange has NO position, but Bot thinks it's OPEN (Ghost Position)
            elif not real_pos and bot.position != 0:
                logger.warning(f"👻 [SYNC] Ghost position detected for {sym}. Closing in DB/Memory.")
                db.log_trade_close(sym, bot.last_price or 0, 0, 0)
                await pm.update_balance_after_trade(sym, 0)
                
                bot.position = 0
                bot.sl_order_id = None
                bot.persist_state()
                msg = f"👻 [SYNC] Cleared ghost {sym} position (Exchange was already closed)."
                report.append(msg)

            # Case C: Both have position, check for quantity drift
            elif real_pos and bot.position != 0:
                real_qty = abs(float(real_pos['contracts']))
                if abs(bot.quantity - real_qty) / (real_qty or 1) > 0.01: # 1% 이상 차이 시
                    logger.warning(f"⚖️ [SYNC] Qty drift for {sym}: Bot({bot.quantity}) vs Exch({real_qty}). Correcting.")
                    bot.quantity = real_qty
                    bot.persist_state()
                    report.append(f"⚖️ [SYNC] Corrected quantity drift for {sym}.")

        if notifier and report:
            notifier.notify_status("🔄 *System Auto-Sync Report*\n" + "\n".join([f"• {m}" for m in report]))
        
        logger.info("✅ [SYNC] Synchronization complete.")
        return len(report) > 0
    except Exception as e:
        logger.error(f"❌ [SYNC] Sync failed: {e}", exc_info=True)
        if notifier: notifier.notify_error(f"🚨 *[SYNC ERROR]* {str(e)[:100]}")
        return False

async def keep_alive_listen_key(exchange, listen_key):
    """Renews the Binance listenKey every 30 minutes."""
    while True:
        await asyncio.sleep(1800)
        try:
            await exchange.fapiPrivatePutListenKey()
            logger.info("🔑 User Data Stream (listenKey) Renewed.")
        except Exception as e:
            logger.error(f"❌ Failed to renew listenKey: {e}")

async def main():
    loop = asyncio.get_running_loop()
    exchange = ccxt.binance({
        'apiKey': CONFIG["BINANCE_API_KEY"], 
        'secret': CONFIG["BINANCE_SECRET"], 
        'options': {'defaultType': 'future'}, 
        'enableRateLimit': True
    })
    db, pm, notifier = DBManager(), PortfolioManagerAsync(exchange, CONFIG), TelegramNotifier()
    notifier.set_commands()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop, notifier, exchange)))
    
    try:
        symbols = CONFIG.get("SYMBOLS_LIST", [])
        if not symbols:
            logger.error("❌ No symbols found in SYMBOLS_LIST. Check config.yaml."); return
            
        # 1. Parallel Initialization
        logger.info(f"🔄 Initializing {len(symbols)} symbols in parallel...")
        bots = {}
        init_tasks = []
        for s in symbols:
            bot_instance = SymbolBotAsync(s, exchange, pm, notifier, db)
            bots[s.replace('/', '').lower()] = bot_instance
            init_tasks.append(bot_instance.initialize())
        
        await asyncio.gather(*init_tasks)

        # 2. DB Startup Sync
        await sync_db_with_exchange(bots, exchange, db, pm)
        
        # Log initial total equity if no history exists to provide a starting point for the dashboard
        if db.get_equity_history(symbol='TOTAL').empty:
            initial_total = await pm.get_total_equity()
            db.log_equity(initial_total, 'TOTAL')
            logger.info(f"📈 Initial TOTAL equity logged: {initial_total:.2f}")
        
        # 3. Connect Public WebSocket
        ws_manager = BinanceWebSocketManager(symbols=symbols)
        asyncio.create_task(ws_manager.connect())
        
        # 4. Setup User Data Stream (Private WebSocket)
        if not CONFIG.get("DRY_RUN", True):
            try:
                listen_key_resp = await exchange.fapiPrivatePostListenKey()
                listen_key = listen_key_resp['listenKey']
                user_ws_manager = BinanceWebSocketManager(listen_key=listen_key)
                asyncio.create_task(user_ws_manager.connect())
                asyncio.create_task(keep_alive_listen_key(exchange, listen_key))
                logger.info("📡 User Data Stream Connected.")
            except Exception as e:
                logger.error(f"❌ Failed to start User Data Stream: {e}")
                user_ws_manager = None
        else:
            user_ws_manager = None

        asyncio.create_task(handle_commands(bots, notifier, pm))
        asyncio.create_task(heartbeat_loop(bots, notifier, pm))
        asyncio.create_task(auto_sentinel_loop(bots, notifier, pm))
        asyncio.create_task(auto_sync_loop(bots, exchange, db, pm, notifier))
        
        logger.info(f"🚀 v{CONFIG['VERSION']}-async Engine Started for: {symbols}")
        notifier.notify_status(f"🛰️ The Sentinel Active (v{CONFIG['VERSION']})")
        await send_summary(bots, notifier, pm)
        
        # 5. Main Event Loop - Public Streams
        async def public_stream_loop():
            while True:
                msg = await ws_manager.get_next_message()
                if not msg: continue
                symbol_key = msg.get('s', '').lower()
                if symbol_key in bots:
                    bot = bots[symbol_key]
                    stream = msg.get('e')
                    if stream == 'markPriceUpdate': await bot.on_mark_price_update(float(msg['p']))
                    elif stream == 'kline': await bot.on_kline_update(msg['k']['i'], msg['k'])

        # 6. Main Event Loop - Private Stream (Order Updates)
        async def private_stream_loop():
            if not user_ws_manager: return
            while True:
                msg = await user_ws_manager.get_next_message()
                if not msg: continue
                # Binance User Data Stream event 'ORDER_TRADE_UPDATE' -> 'e': 'ORDER_TRADE_UPDATE'
                if msg.get('e') == 'ORDER_TRADE_UPDATE':
                    order_data = msg.get('o', {})
                    symbol_key = order_data.get('s', '').lower()
                    if symbol_key in bots:
                        await bots[symbol_key].on_order_update(order_data)

        # Run both loops concurrently
        await asyncio.gather(public_stream_loop(), private_stream_loop())

    except asyncio.CancelledError: pass
    except Exception as e:
        logger.error(f"💥 FATAL ERROR: {e}", exc_info=True)
        notifier.notify_error(f"🚨 *[CRASH]* {str(e)[:200]}")
    finally:
        await exchange.close()
        logger.info("📡 Exchange connection closed.")

import signal
if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as fatal_e: print(f"Final Fallback: {fatal_e}")
