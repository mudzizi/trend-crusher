import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import logging
import signal
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
        
        side = 'buy' if direction == 1 else 'sell'
        try:
            if self.settings["DRY_RUN"]:
                self.active_retest_order_id = "DRY_RETEST"
                self.entry_price = target_price if direction == 1 else -target_price
            else:
                self.logger.info(f"🎣 Retest MAKER: {side.upper()} at {target_price:,.2f}")
                order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'limit', side, qty, target_price, {'postOnly': True})
                self.active_retest_order_id = order['id']
            self.retest_order_ts, self.sl_price, self.quantity = datetime.now(), sl_price, qty
        except Exception as e: self.logger.error(f"Retest error: {e}")

    async def manage_sniper_ambush(self, direction, target_price, atr):
        if self.active_sniper_order_id: return
        self.sl_price = target_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else target_price + (atr * self.settings["INITIAL_SL_ATR"])
        qty = await self.pm.calculate_order_qty(self.symbol, target_price, self.sl_price)
        if qty is None or (isinstance(qty, (int, float)) and qty <= 0): return
        
        side = 'buy' if direction == 1 else 'sell'
        try:
            self.logger.info(f"🏹 Sniper: {side.upper()} LIMIT at {target_price:,.2f}")
            order = await self.retry_api_call(self.exchange.create_limit_order, self.symbol, side, qty, target_price)
            self.active_sniper_order_id, self.quantity = order['id'], qty
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

            self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"])
            self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"])
            self._update_indicators()
            self.logger.info(f"📊 Indicators Initialized")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize {self.symbol}: {e}")
            raise e

    def _update_indicators(self):
        if self.ohlcv_1h is not None and self.ohlcv_4h is not None:
            self.df_indicators = self.engine.calculate_indicators(self.ohlcv_1h, self.ohlcv_4h, self.settings)

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
            # Update the last candle with real-time data
            if kline_ts == target_df.loc[last_idx, 'timestamp']:
                target_df.loc[last_idx, ['open', 'high', 'low', 'close', 'volume']] = [
                    float(kline['o']), float(kline['h']), float(kline['l']), self.last_price, float(kline['v'])
                ]
            elif kline_ts > target_df.loc[last_idx, 'timestamp']:
                # New candle started
                if is_signal_tf: self.ohlcv_1h = await self.fetch_ohlcv(tf)
                else: self.ohlcv_4h = await self.fetch_ohlcv(tf)
                self.logger.info(f"🕯️ New Candle ({tf}) synced at {kline_ts}")
            
            # Re-calculate indicators with the latest price in the dataframe
            self._update_indicators()

            # Perform entry/exit checks on every update (intra-bar)
            if not kline['x']:
                if self.position != 0: await self.check_exit()
                else: await self.check_entry()
        except Exception as e:
            self.logger.error(f"⚠️ Error updating OHLCV buffer for {self.symbol}: {e}")

    async def on_mark_price_update(self, price):
        self.last_price = price
        # Record status for dashboard first
        await self._record_live_status()
        
        if self.position != 0:
            await self.check_exit()
        else:
            if self.active_retest_order_id:
                if self.settings["DRY_RUN"]:
                    is_filled = False
                    if self.entry_price > 0 and price <= self.entry_price: is_filled = True
                    elif self.entry_price < 0 and price >= abs(self.entry_price): is_filled = True
                    if is_filled:
                        self.logger.info(f"🧪 [DRY RUN] Retest Maker FILLED at {price}")
                        direction = 1 if self.entry_price > 0 else -1
                        self.entry_price = abs(self.entry_price)
                        await self._on_fill_success(direction)
                        self.active_retest_order_id = None
                else:
                    await self.check_retest_fill()
            elif self.active_sniper_order_id:
                await self.check_sniper_fill()
            await self.check_entry()

    async def _record_live_status(self):
        if self.df_indicators is None or self.df_indicators.empty: return
        try:
            row = self.df_indicators.iloc[-1]
            last_price = self.last_price
            
            # 1. Volume Proximity (Current 1m sum vs Target)
            # Find the starting index of the current 1h candle in the 1m data buffer if available, 
            # but for simplicity in Live, we use the pre-calculated 'volume' in row which includes intra-bar updates.
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
            # Weighted: Price Prox (40%), Vol (30%), ADX (30%)
            score = (prox_ratio * 40) + (vol_ratio * 30) + (adx_ratio * 30)
            if not trend_ok: score *= 0.5 # Penalty for wrong trend
            
            self.db.update_live_status(
                self.symbol, vol_ratio, adx_ratio, prox_ratio, trend_ok, score, 
                last_price, upper, lower
            )
        except Exception as e:
            self.logger.error(f"Error recording live status: {e}")

    async def check_sniper_fill(self):
        if self.settings["DRY_RUN"]: return
        try:
            order = await self.retry_api_call(self.exchange.fetch_order, self.active_sniper_order_id, self.symbol)
            if order and isinstance(order, dict) and order['status'] == 'closed':
                self.logger.info(f"🎯 Sniper Order FILLED for {self.symbol}!")
                self.quantity = float(order.get('filled', order.get('amount', self.quantity)))
                self.entry_price = float(order.get('average', order.get('price', self.entry_price)))
                direction = 1 if order['side'] == 'buy' else -1
                await self._on_fill_success(direction)
                self.active_sniper_order_id = None
        except Exception as e:
            self.logger.error(f"Error checking sniper fill: {e}")

    async def check_retest_fill(self):
        if not self.active_retest_order_id: return
        if self.retest_order_ts:
            elapsed = (datetime.now() - self.retest_order_ts).total_seconds()
            if elapsed > 14400:
                self.logger.info(f"⌛ Retest order TIMEOUT (4h) for {self.symbol}. Cancelling.")
                await self.cancel_retest_order()
                return
        try:
            order = await self.retry_api_call(self.exchange.fetch_order, self.active_retest_order_id, self.symbol)
            if order and isinstance(order, dict) and order['status'] == 'closed':
                self.logger.info(f"✅ Retest Maker Order FILLED for {self.symbol}!")
                self.quantity = float(order.get('filled', order.get('amount', self.quantity)))
                self.entry_price = float(order.get('average', order.get('price', self.entry_price)))
                direction = 1 if order['side'] == 'buy' else -1
                await self._on_fill_success(direction)
                self.active_retest_order_id = None
                self.retest_order_ts = None
        except Exception as e:
            self.logger.error(f"Error checking retest fill: {e}")

    async def _on_fill_success(self, direction):
        side_str = "LONG" if direction == 1 else "SHORT"
        try:
            params = {'stopPrice': self.sl_price, 'reduceOnly': True}
            sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
            self.sl_order_id = sl_order['id']
        except Exception as sl_err:
            self.logger.error(f"🚨 CRITICAL: SL failed: {sl_err}. EMERGENCY LIQUIDATION!")
            await self.exchange.create_market_order(self.symbol, 'sell' if direction == 1 else 'buy', self.quantity)
            return
        self.position = direction
        self.max_price_seen = self.entry_price
        self.min_price_seen = self.entry_price
        self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
        self.persist_state()
        self.notifier.notify_entry(f"🚀 {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)

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
            atr = row['atr'] # Used for SL distance inside manage_sniper_ambush
            await self.manage_sniper_ambush(direction, target_p, atr)
        elif sig_type == 'MARKET':
            direction = 1 if target_p > row['ema_h'] else -1
            await self.execute_entry(direction, row['atr'])

    async def check_exit(self):
        if self.df_indicators is None or self.position == 0: return
        row = self.df_indicators.iloc[-1]
        
        state = {
            'position': self.position,
            'entry_price': self.entry_price,
            'max_price_seen': self.max_price_seen,
            'min_price_seen': self.min_price_seen,
            'sl_price': self.sl_price
        }
        
        if self.engine.check_exit_signal(row, self.last_price, state, self.settings):
            await self.execute_exit()
        else:
            # Update extremes if still in position
            if self.position == 1: self.max_price_seen = max(self.max_price_seen, self.last_price)
            else: self.min_price_seen = min(self.min_price_seen, self.last_price)

    async def execute_entry(self, direction, atr):
        side_str = "LONG" if direction == 1 else "SHORT"
        self.sl_price = float(self.last_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else self.last_price + (atr * self.settings["INITIAL_SL_ATR"]))
        
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if qty is None or qty <= 0:
            self.logger.warning(f"🚫 Entry skipped: Invalid quantity ({qty}) for {self.symbol}"); return
        
        self.quantity = float(qty)
        try:
            if not self.settings["DRY_RUN"]:
                side = 'buy' if direction == 1 else 'sell'
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, self.quantity)
                
                # IMPORTANT: Use actual exchange-reported fill price and quantity
                if order is None or not isinstance(order, dict):
                    self.logger.error(f"⚠️ Exchange returned invalid order response for {self.symbol} during entry. Using fallback.")
                    self.entry_price = self.last_price
                else:
                    self.entry_price = float(order.get('average', order.get('price', self.last_price)))
                    self.quantity = float(order.get('filled', self.quantity))
                
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
        except Exception as e: self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        # Guard against ZeroDivision or invalid state
        if self.position == 0: return
        
        try:
            pnl_pct = 0
            pnl_usdt = 0
            exit_price = self.last_price
            
            if not self.settings["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                # 1. Execute Market Order
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, self.quantity)
                
                # 2. VERIFY: Did the position actually close on the exchange?
                # We wait a brief moment for exchange synchronization
                await asyncio.sleep(1)
                positions = await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])
                pos = next((p for p in positions if p['symbol'] == self.symbol), None)
                
                if pos and float(pos['contracts']) != 0:
                    self.logger.error(f"🚨 EXIT FAILED: Position still exists on exchange for {self.symbol} ({pos['contracts']} left). Retrying...")
                    # Try one more time with the EXACT remaining contracts
                    side = 'sell' if float(pos['contracts']) > 0 else 'buy'
                    await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, abs(float(pos['contracts'])))
                
                if order is None or not isinstance(order, dict):
                    exit_price = self.last_price
                    filled_qty = self.quantity
                    fee = exit_price * filled_qty * 0.0005
                else:
                    exit_price = float(order.get('average', order.get('price', self.last_price)))
                    filled_qty = float(order.get('filled', self.quantity))
                    fee = order.get('fee', {}).get('cost', exit_price * filled_qty * 0.0005)
                
                pnl_usdt = (exit_price - self.entry_price) * filled_qty * self.position
                pnl_usdt -= float(fee)
                
                if self.sl_order_id:
                    try: await self.retry_api_call(self.exchange.cancel_order, self.sl_order_id, self.symbol)
                    except: pass
            else:
                pnl_usdt = (exit_price - self.entry_price) * self.quantity * self.position
            
            if self.entry_price > 0:
                pnl_pct = ((exit_price / self.entry_price) - 1) * 100 * self.position
            
            # 5. Final State Update
            self.db.log_trade_close(self.symbol, exit_price, pnl_pct, pnl_usdt)
            await self.pm.update_balance_after_trade(self.symbol, pnl_usdt)
            new_total_equity = await self.pm.get_total_equity()
            self.db.log_equity(new_total_equity, 'TOTAL')
            
            self.position, self.sl_order_id = 0, None
            self.persist_state()
            self.notifier.notify_exit(f"Async {self.symbol}", exit_price, pnl_pct, pnl_usdt)
        except Exception as e: 
            self.logger.error(f"Exit error: {e}")
            # If exit fails, we DON'T set self.position = 0, so it will try again next tick

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
                
                if order is None or not isinstance(order, dict):
                    self.logger.error(f"⚠️ Exchange returned invalid order response for {self.symbol} during force exit.")
                    exit_price = self.last_price
                    fee = exit_price * qty * 0.0005
                else:
                    exit_price = float(order.get('average', order.get('price', self.last_price)))
                    fee = order.get('fee', {}).get('cost', exit_price * qty * 0.0005)
                
                pnl_usdt = (exit_price - self.entry_price) * qty * self.position
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
        await asyncio.sleep(10)

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
    reply_markup = {"keyboard": [[{"text": "/status"}, {"text": "/retest_on"}, {"text": "/retest_off"}], [{"text": "/sniper_on"}, {"text": "/sniper_off"}, {"text": "/stop"}], [{"text": "/resume"}, {"text": "/close_all"}]], "resize_keyboard": True}
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

async def sync_db_with_exchange(bots, exchange, db, pm):
    """
    Startup synchronization: Closes 'OPEN' trades in DB if they don't exist on the exchange.
    """
    logger.info("🔍 Synchronizing DB with actual exchange positions...")
    try:
        # 1. Fetch active trades from DB
        active_trades = db.get_active_trades()
        if active_trades.empty:
            logger.info("✅ No active trades in DB to sync.")
            return

        # 2. Fetch real positions from exchange
        # Note: We fetch all symbols to be efficient
        all_positions = await exchange.fetch_positions()
        real_active_symbols = {p['symbol'] for p in all_positions if float(p['contracts']) != 0}

        for _, trade in active_trades.iterrows():
            sym = trade['symbol']
            if sym not in real_active_symbols:
                logger.warning(f"👻 Ghost position detected for {sym} in DB. Closing automatically.")
                # Close in DB with fallback values since we don't have the real exit price
                db.log_trade_close(sym, 0, 0, 0)
                await pm.update_balance_after_trade(sym, 0)
                
                # If a bot object exists for this symbol, ensure its state is also reset
                if sym.replace('/', '').lower() in bots:
                    bot_obj = bots[sym.replace('/', '').lower()]
                    bot_obj.position = 0
                    bot_obj.persist_state()
        
        logger.info("✅ DB Synchronization complete.")
    except Exception as e:
        logger.error(f"❌ DB Sync failed: {e}")

async def main():
    loop = asyncio.get_running_loop()
    exchange = ccxt.binance({'apiKey': CONFIG["BINANCE_API_KEY"], 'secret': CONFIG["BINANCE_SECRET"], 'options': {'defaultType': 'future'}, 'enableRateLimit': True})
    db, pm, notifier = DBManager(), PortfolioManagerAsync(exchange, CONFIG), TelegramNotifier()
    notifier.set_commands()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop, notifier, exchange)))
    
    try:
        symbols = CONFIG.get("SYMBOLS_LIST", [])
        if not symbols:
            logger.error("❌ No symbols found in SYMBOLS_LIST. Check config.yaml."); return
# Map 'btcusdt' (WS stream key) to Bot instance
bots = {}
for s in symbols:
    bot_instance = SymbolBotAsync(s, exchange, pm, notifier, db)
    await bot_instance.initialize()
    ws_key = s.replace('/', '').lower()
    bots[ws_key] = bot_instance

# --- [DB Startup Sync] ---
await sync_db_with_exchange(bots, exchange, db, pm)
# -------------------------

# Connect WebSocket
        ws_manager = BinanceWebSocketManager(symbols)
        asyncio.create_task(ws_manager.connect())
        asyncio.create_task(handle_commands(bots, notifier, pm))
        asyncio.create_task(heartbeat_loop(bots, notifier, pm))
        asyncio.create_task(auto_sentinel_loop(bots, notifier, pm))
        
        logger.info(f"🚀 v{CONFIG['VERSION']}-async Engine Started for: {symbols}")
        notifier.notify_status(f"🛰️ The Sentinel Active (v{CONFIG['VERSION']})")
        await send_summary(bots, notifier, pm)
        
        while True:
            try:
                msg = await ws_manager.get_next_message()
                if not msg: continue
                
                stream = msg.get('e')
                symbol_key = msg.get('s', '').lower()
                
                if symbol_key in bots:
                    bot = bots[symbol_key]
                    if stream == 'markPriceUpdate': 
                        await bot.on_mark_price_update(float(msg['p']))
                    elif stream == 'kline': 
                        await bot.on_kline_update(msg['k']['i'], msg['k'])
            except Exception as loop_e:
                logger.error(f"⚠️ Error in main event loop: {loop_e}")
                await asyncio.sleep(1)
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
