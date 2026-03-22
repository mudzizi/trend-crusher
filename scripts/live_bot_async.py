import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import os
import logging
from datetime import datetime
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.strategy import TrendCrusherV2
from src.telegram_utils import TelegramNotifier

# ... (Logging setup remains same)

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
            if kline_ts == target_df.loc[last_idx, 'timestamp']:
                target_df.loc[last_idx, ['open', 'high', 'low', 'close', 'volume']] = [float(kline['o']), float(kline['h']), float(kline['l']), self.last_price, float(kline['v'])]
            elif kline_ts > target_df.loc[last_idx, 'timestamp']:
                if is_signal_tf: self.ohlcv_1h = await self.fetch_ohlcv(tf)
                else: self.ohlcv_4h = await self.fetch_ohlcv(tf)
                self.logger.info(f"🕯️ New Candle ({tf}) synced at {kline_ts}")
            
            self._update_indicators()

            if not kline['x']:
                if self.position != 0: await self.check_exit()
                else: await self.check_entry()
        except Exception as e:
            self.logger.error(f"⚠️ Error updating OHLCV buffer: {e}")

    # ... (fetch_ohlcv, on_mark_price_update, check_sniper_fill, cancel_retest_order, check_retest_fill, _on_fill_success remain same)

    async def check_entry(self):
        if self.is_halted or self.df_indicators is None: return
        row = self.df_indicators.iloc[-1]
        
        sig_type, target_p, sl_p = self.engine.check_entry_signal(row, self.last_price, self.use_sniper, self.use_retest_maker, self.settings)
        
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
        self.sl_price = self.last_price - (atr * self.settings["INITIAL_SL_ATR"]) if direction == 1 else self.last_price + (atr * self.settings["INITIAL_SL_ATR"])
        qty = await self.pm.calculate_order_qty(self.symbol, self.last_price, self.sl_price)
        if qty <= 0: return
        self.quantity = qty
        try:
            if not self.settings["DRY_RUN"]:
                side = 'buy' if direction == 1 else 'sell'
                order = await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, self.quantity)
                self.quantity = float(order.get('filled', self.quantity))
                try: await self.retry_api_call(self.exchange.create_order, self.symbol, 'STOP_MARKET', 'sell' if direction == 1 else 'buy', self.quantity, None, {'stopPrice': self.sl_price, 'reduceOnly': True})
                except Exception as sl_err:
                    self.logger.error(f"🚨 CRITICAL SL FAILED: {sl_err}")
                    await self.exchange.create_market_order(self.symbol, 'sell' if direction == 1 else 'buy', self.quantity); return
            self.position, self.entry_price = direction, self.last_price
            self.max_price_seen = self.min_price_seen = self.entry_price
            self.db.log_trade_open(self.symbol, side_str, self.entry_price, self.quantity, 100)
            self.persist_state()
            self.notifier.notify_entry(f"Async {self.symbol} {side_str}", self.entry_price, self.sl_price, 100)
        except Exception as e: self.logger.error(f"Entry error: {e}")

    async def execute_exit(self):
        pnl_pct = ((self.last_price / self.entry_price) - 1) * 100 * self.position
        try:
            if not self.settings["DRY_RUN"]:
                side = 'sell' if self.position == 1 else 'buy'
                await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, self.quantity)
                if self.sl_order_id:
                    try: await self.retry_api_call(self.exchange.cancel_order, self.sl_order_id, self.symbol)
                    except: pass
            self.db.log_trade_close(self.symbol, self.last_price, pnl_pct, 0)
            await self.pm.update_balance_after_trade(self.symbol, 0)
            self.position, self.sl_order_id = 0, None
            self.persist_state()
            self.notifier.notify_exit(f"Async {self.symbol}", self.last_price, pnl_pct, 0)
        except Exception as e: self.logger.error(f"Exit error: {e}")

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
                        notifier.notify_status("⚠️ EMERGENCY SHUTDOWN...")
                        for b in bots.values():
                            if b.position != 0: await b.execute_exit()
                            if b.active_sniper_order_id: await b.cancel_sniper_ambush()
                            if b.active_retest_order_id: await b.cancel_retest_order()
                        os._exit(0)
        except Exception as e: logger.error(f"Command Error: {e}")
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

async def main():
    loop = asyncio.get_running_loop()
    exchange = ccxt.binance({'apiKey': CONFIG["BINANCE_API_KEY"], 'secret': CONFIG["BINANCE_SECRET"], 'options': {'defaultType': 'future'}, 'enableRateLimit': True})
    db, pm, notifier = DBManager(), PortfolioManagerAsync(exchange, CONFIG), TelegramNotifier()
    notifier.set_commands()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop, notifier, exchange)))
    try:
        symbols = CONFIG["SYMBOLS_LIST"]
        bots = {s.replace('/', '').lower(): SymbolBotAsync(s, exchange, pm, notifier, db) for s in symbols}
        for bot in bots.values(): await bot.initialize()
        ws_manager = BinanceWebSocketManager(symbols)
        asyncio.create_task(ws_manager.connect())
        asyncio.create_task(handle_commands(bots, notifier, pm))
        asyncio.create_task(heartbeat_loop(bots, notifier, pm))
        asyncio.create_task(auto_sentinel_loop(bots, notifier, pm))
        logger.info(f"🚀 v{CONFIG['VERSION']}-async Engine Started.")
        notifier.notify_status(f"🛰️ The Sentinel Active (v{CONFIG['VERSION']})")
        await send_summary(bots, notifier, pm)
        while True:
            try:
                msg = await ws_manager.get_next_message()
                stream, symbol_key = msg.get('e'), msg.get('s', '').lower()
                if symbol_key in bots:
                    bot = bots[symbol_key]
                    if stream == 'markPriceUpdate': await bot.on_mark_price_update(float(msg['p']))
                    elif stream == 'kline': await bot.on_kline_update(msg['k']['i'], msg['k'])
            except Exception as loop_e:
                logger.error(f"⚠️ Error in main event loop: {loop_e}")
                await asyncio.sleep(1)
    except asyncio.CancelledError: pass
    except Exception as e:
        logger.error(f"💥 FATAL ERROR: {e}", exc_info=True)
        notifier.notify_error(f"🚨 *[CRASH]* {str(e)[:200]}")
    finally: await exchange.close()

import signal
if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as fatal_e: print(f"Final Fallback: {fatal_e}")
