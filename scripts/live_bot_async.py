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
        self.is_halted = False # If true, skip new entries
        self.pending_settings = None # v10: Store unapproved optimization results
        self.active_sniper_order_id = None # v11: Track pre-emptive limit order
        self.use_sniper = True # v11: Remote kill switch for Sniper logic
        
        # Internal state for incremental indicators
        self.ohlcv_1h = None
        self.ohlcv_4h = None
        self.last_price = 0

    def hot_reload_settings(self, new_params):
        """Updates internal settings without restarting the bot."""
        self.settings.update(new_params)
        self.logger.info(f"⚙️ Settings Hot-Reloaded: {new_params}")

    async def retry_api_call(self, func, *args, max_retries=3, delay=2, **kwargs):
        for i in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if i == max_retries - 1: raise e
                self.logger.warning(f"⚠️ API Error: {e}. Retrying {i+1}/{max_retries}...")
                await asyncio.sleep(delay * (i + 1))

    async def initialize(self):
        """Initial sync from DB and REST API."""
        try:
            # 1. State recovery
            state = self.db.get_bot_state(self.symbol)
            if state:
                self.position = int(state['position'])
                self.entry_price = float(state['entry_price'])
                self.quantity = float(state['quantity'])
                self.max_price_seen = float(state['max_price'])
                self.sl_order_id = state['sl_order_id']
                self.logger.info(f"💾 Recovered: Pos={self.position}, Entry={self.entry_price}")

            # 2. Initial OHLCV fetch via REST with retry
            self.ohlcv_1h = await self.fetch_ohlcv(self.settings["SIGNAL_TIMEFRAME"])
            self.ohlcv_4h = await self.fetch_ohlcv(self.settings["TREND_TIMEFRAME"])
            self.logger.info(f"📊 Indicators Initialized")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize {self.symbol}: {e}")
            raise e

    async def on_kline_update(self, tf, kline):
        """Update local OHLCV buffer when a candle closes or updates."""
        if kline['x']: # Candle is closed
            self.logger.info(f"🕯️ Candle Closed ({tf}): Updating indicators...")
            try:
                if tf == self.settings["SIGNAL_TIMEFRAME"]:
                    self.ohlcv_1h = await self.fetch_ohlcv(tf)
                else:
                    self.ohlcv_4h = await self.fetch_ohlcv(tf)
            except Exception as e:
                self.logger.error(f"⚠️ Failed to update OHLCV on candle close: {e}")

    async def fetch_ohlcv(self, tf, limit=100):
        ohlcv = await self.retry_api_call(self.exchange.fetch_ohlcv, self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def on_mark_price_update(self, price):
        """Triggered by WebSocket Mark Price stream."""
        self.last_price = price
        if self.position != 0:
            await self.check_exit()
        else:
            if self.active_sniper_order_id:
                await self.check_sniper_fill()
            await self.check_entry()

    async def check_sniper_fill(self):
        """Checks if the active sniper limit order has been filled."""
        if self.settings["DRY_RUN"]: return # Simulate in check_entry for dry run
        try:
            order = await self.retry_api_call(self.exchange.fetch_order, self.active_sniper_order_id, self.symbol)
            if order['status'] == 'closed':
                self.logger.info(f"🎯 Sniper Order FILLED for {self.symbol}!")
                self.quantity = float(order.get('filled', order.get('amount')))
                self.entry_price = float(order['average'])
                direction = 1 if order['side'] == 'buy' else -1
                side_str = "LONG" if direction == 1 else "SHORT"
                
                # Atomic SL Placement
                try:
                    params = {'stopPrice': self.sl_price, 'reduceOnly': True}
                    sl_order = await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, params)
                    self.sl_order_id = sl_order['id']
                except Exception as sl_err:
                    self.logger.error(f"🚨 CRITICAL: SL placement failed after Sniper Fill: {sl_err}. EMERGENCY LIQUIDATION!")
                    await self.exchange.create_market_order(self.symbol, 'sell' if direction == 1 else 'buy', self.quantity)
                    self.active_sniper_order_id = None
                    return
                
                self.position = direction
                self.max_price_seen = self.entry_price
                self.min_price_seen = self.entry_price
                self.active_sniper_order_id = None
                
                self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
                self.persist_state()
                self.notifier.notify_entry(f"🎯 Sniper {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)
                
        except Exception as e:
            self.logger.error(f"Error checking sniper fill: {e}")

    async def check_entry(self):
        if self.is_halted: return
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
        
        # The 4 Pillars
        momentum_ok = curr_vol > (avg_vol * self.settings["VOL_MULTIPLIER"])
        trend_ok = adx > self.settings["ADX_FILTER_LEVEL"]
        
        top_level = upper.iloc[-1]
        bottom_level = lower.iloc[-1]
        
        dist_top = abs(self.last_price - top_level) / (self.last_price + 1e-10)
        dist_bottom = abs(self.last_price - bottom_level) / (self.last_price + 1e-10)
        prox_threshold = self.settings.get("SNIPER_PROXIMITY_PCT", 0.005)
        
        long_conditions_met = momentum_ok and trend_ok and self.last_price > ema_4h and dist_top <= prox_threshold
        short_conditions_met = momentum_ok and trend_ok and self.last_price < ema_4h and dist_bottom <= prox_threshold
        
        # Classic breakout fallback & DRY_RUN simulation
        if momentum_ok and trend_ok and self.last_price > ema_4h and self.last_price > top_level:
            if not self.active_sniper_order_id:
                await self.execute_entry(1, atr)
            return
        elif momentum_ok and trend_ok and self.last_price < ema_4h and self.last_price < bottom_level:
            if not self.active_sniper_order_id:
                await self.execute_entry(-1, atr)
            return

        if self.use_sniper and not self.settings["DRY_RUN"]:
            if long_conditions_met:
                await self.manage_sniper_ambush(1, top_level, atr)
            elif short_conditions_met:
                await self.manage_sniper_ambush(-1, bottom_level, atr)
            elif self.active_sniper_order_id:
                # Conditions broke, abort sniper
                self.logger.info(f"🚫 Sniper conditions weakened. Aborting ambush for {self.symbol}.")
                await self.cancel_sniper_ambush()

    async def manage_sniper_ambush(self, direction, target_price, atr):
        if self.active_sniper_order_id: return # Already ambushing
        
        # Calculate size
        self.sl_price = target_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else target_price + (atr * self.settings["INITIAL_SL_ATR"])
        qty = await self.pm.calculate_order_qty(self.symbol, target_price, self.sl_price)
        if qty <= 0: return
        
        side = 'buy' if direction == 1 else 'sell'
        try:
            self.logger.info(f"🏹 Sniper Ambush Set! {side.upper()} LIMIT at {target_price:,.2f} for {self.symbol}")
            order = await self.retry_api_call(self.exchange.create_limit_order, self.symbol, side, qty, target_price)
            self.active_sniper_order_id = order['id']
            self.quantity = qty
        except Exception as e:
            self.logger.error(f"Failed to place sniper limit order: {e}")

    async def cancel_sniper_ambush(self):
        if not self.active_sniper_order_id: return
        try:
            await self.retry_api_call(self.exchange.cancel_order, self.active_sniper_order_id, self.symbol)
            self.logger.info(f"♻️ Sniper Order Cancelled for {self.symbol}")
        except ccxt.OrderNotFound:
            pass # Might have just filled
        except Exception as e:
            self.logger.warning(f"Error cancelling sniper order: {e}")
        self.active_sniper_order_id = None

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
                    return

            self.position = direction
            self.entry_price = self.last_price
            self.max_price_seen = self.entry_price
            self.min_price_seen = self.entry_price
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

    def hot_reload_settings(self, new_params):
        """Updates internal settings without restarting the bot."""
        self.settings.update(new_params)
        self.logger.info(f"⚙️ Settings Hot-Reloaded: {new_params}")

async def handle_commands(bots, notifier, pm):
    """Background task to poll and process Telegram commands."""
    from src.optimizer_engine import OptimizerEngine
    offset = None
    optimizer = OptimizerEngine(config=CONFIG)
    logger.info("📡 Command Listener active (v10 Sentinel).")
    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for result in updates.get("result", []):
                    offset = result["update_id"] + 1
                    message = result.get("message", {})
                    text = message.get("text", "")
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    
                    if chat_id != str(CONFIG["TELEGRAM_CHAT_ID"]): continue
                    
                    parts = text.split()
                    if not parts: continue
                    cmd = parts[0].lower()
                    
                    if cmd == "/status":
                        await send_summary(bots, notifier, pm)
                    elif cmd == "/optimize":
                        if len(parts) < 2:
                            notifier.notify_status("Usage: /optimize [SYMBOL]")
                            continue
                        symbol = parts[1].upper()
                        bot_key = symbol.replace('/', '').lower()
                        if bot_key in bots:
                            notifier.notify_status(f"🧠 Sentinel is studying {symbol}... (approx 30s)")
                            best = await optimizer.find_best_params(symbol)
                            if best:
                                # Store as pending
                                bots[bot_key].pending_settings = {
                                    "VOL_MULTIPLIER": best['vol_m'],
                                    "ADX_FILTER_LEVEL": best['adx_f'],
                                    "EMA_TREND_PERIOD": best['ema_p']
                                }
                                report = {
                                    "Proposal": "OPTIMIZE",
                                    "New Vol": best['vol_m'],
                                    "New ADX": best['adx_f'],
                                    "New EMA": best['ema_p'],
                                    "Est. Return": f"{best['return']:.2f}%",
                                    "Est. MDD": f"{best['mdd']:.2f}%",
                                    "Action": f"To apply, send: /apply {symbol}"
                                }
                                notifier.send_report(f"🚀 Sentinel Proposal: {symbol}", report)
                            else:
                                notifier.notify_error(f"Failed to optimize {symbol}.")
                        else:
                            notifier.notify_error(f"Bot for {symbol} not found.")
                    
                    elif cmd == "/apply":
                        if len(parts) < 2:
                            notifier.notify_status("Usage: /apply [SYMBOL]")
                            continue
                        symbol = parts[1].upper()
                        bot_key = symbol.replace('/', '').lower()
                        if bot_key in bots and bots[bot_key].pending_settings:
                            new_settings = bots[bot_key].pending_settings
                            bots[bot_key].hot_reload_settings(new_settings)
                            bots[bot_key].pending_settings = None # Clear queue
                            notifier.notify_status(f"✅ Optimization applied to {symbol}!")
                        else:
                            notifier.notify_error(f"No pending proposal for {symbol}.")

                    elif cmd == "/reject":
                        if len(parts) < 2:
                            notifier.notify_status("Usage: /reject [SYMBOL]")
                            continue
                        symbol = parts[1].upper()
                        bot_key = symbol.replace('/', '').lower()
                        if bot_key in bots:
                            bots[bot_key].pending_settings = None
                            notifier.notify_status(f"❌ Proposal for {symbol} rejected.")

                    elif cmd == "/stop":
                        for bot in bots.values(): bot.is_halted = True
                        notifier.notify_status("🛑 New entries HALTED for all symbols.")
                    elif cmd == "/resume":
                        for bot in bots.values(): bot.is_halted = False
                        notifier.notify_status("▶️ New entries RESUMED for all symbols.")
                    elif cmd == "/close_all":
                        notifier.notify_status("⚠️ EMERGENCY: Closing all positions and shutting down...")
                        for bot in bots.values():
                            if bot.position != 0: await bot.execute_exit()
                            if bot.active_sniper_order_id: await bot.cancel_sniper_ambush()
                        notifier.notify_status("💀 All positions closed. Bot stopping.")
                        os._exit(0)
                    elif cmd == "/sniper_off":
                        for bot in bots.values(): 
                            bot.use_sniper = False
                            if bot.active_sniper_order_id: await bot.cancel_sniper_ambush()
                        notifier.notify_status("🔕 Sniper Mode DISABLED. Reverting to market-only breakouts.")
                    elif cmd == "/sniper_on":
                        for bot in bots.values(): bot.use_sniper = True
                        notifier.notify_status("🎯 Sniper Mode ENABLED. Ready for precise limit entries.")
                        
        except Exception as e:
            logger.error(f"Command Error: {e}")
        await asyncio.sleep(10)

async def auto_sentinel_loop(bots, notifier, pm):
    """Weekly task to scan and propose optimizations for all symbols."""
    from src.optimizer_engine import OptimizerEngine
    optimizer = OptimizerEngine(config=CONFIG)
    while True:
        # Wait for 7 days
        await asyncio.sleep(7 * 24 * 3600)
        logger.info("🛰️ Sentinel is performing weekly patrol...")
        notifier.notify_status("🛰️ Sentinel is performing weekly optimization scan for all symbols.")
        
        for symbol_key, bot in bots.items():
            try:
                best = await optimizer.find_best_params(bot.symbol)
                if best:
                    bot.pending_settings = {
                        "VOL_MULTIPLIER": best['vol_m'],
                        "ADX_FILTER_LEVEL": best['adx_f'],
                        "EMA_TREND_PERIOD": best['ema_p']
                    }
                    report = {
                        "Patrol": "WEEKLY_SCAN",
                        "New Vol": best['vol_m'],
                        "New ADX": best['adx_f'],
                        "New EMA": best['ema_p'],
                        "Est. Return": f"{best['return']:.2f}%",
                        "Est. MDD": f"{best['mdd']:.2f}%",
                        "Action": f"To apply, send: /apply {bot.symbol}"
                    }
                    notifier.send_report(f"🛰️ Sentinel Patrol Report: {bot.symbol}", report)
                await asyncio.sleep(60) # Delay between symbols to avoid API limits
            except Exception as e:
                logger.error(f"Sentinel Patrol Error for {bot.symbol}: {e}")

async def send_summary(bots, notifier, pm):
    """Sends a detailed summary of the entire portfolio."""
    report = {}
    active_count = 0
    total_value = 0
    
    for sym, bot in bots.items():
        # Get current logical capital for this symbol
        capital = await pm.get_total_equity(bot.symbol)
        total_value += capital
        
        status = "IDLE"
        if bot.position != 0:
            active_count += 1
            pnl = ((bot.last_price / bot.entry_price) - 1) * 100 * bot.position
            status = f"{'LONG' if bot.position==1 else 'SHORT'} ({pnl:+.2f}%)"
        elif bot.active_sniper_order_id:
            status = "🎯 AMBUSHING (Limit Set)"
        
        # v10: Indicate pending proposals
        if bot.pending_settings:
            status += " 🧠(PENDING)"
            
        report[f"{bot.symbol} (${capital:,.0f})"] = status
    
    report["---"] = "---"
    report["Total Portfolio"] = f"${total_value:,.2f}"
    report["Active Positions"] = active_count
    
    # Get states from the first bot
    first_bot = next(iter(bots.values())) if bots else None
    report["Halted"] = first_bot.is_halted if first_bot else False
    report["Sniper Mode"] = "ON" if first_bot and first_bot.use_sniper else "OFF"
    
    notifier.send_report(f"Portfolio Heartbeat (v{CONFIG['VERSION']})", report)

async def heartbeat_loop(bots, notifier, pm):
    """Sends a heartbeat report every hour."""
    while True:
        await asyncio.sleep(3600) # 1 Hour
        await send_summary(bots, notifier, pm)

import signal

# ... (Logging setup remains)

async def shutdown(sig, loop, notifier, exchange):
    """Cleanup tasks and notify on catchable signals (SIGINT, SIGTERM)."""
    logger.warning(f"Received exit signal {sig.name}...")
    try:
        notifier.notify_error(f"💀 *[TERMINATED]* Bot received {sig.name} and is shutting down.")
    except:
        pass
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for t in tasks]
    
    await exchange.close()
    loop.stop()
    logger.info("👋 Cleanup complete. Bot stopped.")

async def main():
    loop = asyncio.get_running_loop()
    exchange = ccxt.binance({
        'apiKey': CONFIG["BINANCE_API_KEY"],
        'secret': CONFIG["BINANCE_SECRET"],
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    
    db = DBManager()
    pm = PortfolioManagerAsync(exchange, CONFIG)
    notifier = TelegramNotifier()
    
    # Register signal handlers for clean exit and notification
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop, notifier, exchange)))

    try:
        symbols = CONFIG["SYMBOLS_LIST"]
        bots = {s.replace('/', '').lower(): SymbolBotAsync(s, exchange, pm, notifier, db) for s in symbols}
        
        for bot in bots.values():
            await bot.initialize()

        ws_manager = BinanceWebSocketManager(symbols)
        asyncio.create_task(ws_manager.connect())
        asyncio.create_task(handle_commands(bots, notifier, pm))
        asyncio.create_task(heartbeat_loop(bots, notifier, pm))
        asyncio.create_task(auto_sentinel_loop(bots, notifier, pm))
        
        logger.info(f"🚀 v{CONFIG['VERSION']}-async Engine Started. Sentinel is watching...")
        notifier.notify_status(f"🛰️ The Sentinel Active (v{CONFIG['VERSION']})")

        while True:
            try:
                msg = await ws_manager.get_next_message()
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
                await asyncio.sleep(1) # Cool down before next message
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"💥 FATAL ERROR: {e}", exc_info=True)
        notifier.notify_error(f"🚨 *[CRASH]* Bot died due to an unexpected error:\n`{str(e)[:200]}`\nCheck logs for details.")
    finally:
        await exchange.close()
        logger.info("👋 Exchange resources released.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as fatal_e:
        # Final fallback for errors outside the async loop
        print(f"Final Fallback: {fatal_e}")
