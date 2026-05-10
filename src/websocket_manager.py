import asyncio
import json
import logging
import time
import os
import traceback
from urllib.parse import quote

import websockets

# --- Account-wide Order Logger Setup ---
os.makedirs("log", exist_ok=True)
order_logger = logging.getLogger("AccountOrders")
order_logger.setLevel(logging.INFO)
if not order_logger.handlers:
    fh = logging.FileHandler("log/account_orders.log")
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    order_logger.addHandler(fh)

logger = logging.getLogger(__name__)

# --- Binance Futures 2026 WebSocket Architecture ---
# As of March 2026, endpoints are specialized for stability and performance.
WS_PUBLIC_BASE = "wss://fstream.binance.com/public"   # High-frequency (Orderbook, etc.)
WS_MARKET_BASE = "wss://fstream.binance.com/market"   # Regular market data (Klines, MarkPrice)
WS_PRIVATE_BASE = "wss://fstream.binance.com/private" # User Data Streams (Order updates)

class BinanceWebSocketManager:
    """
    Async Binance Futures WebSocket manager.
    Migrated to March 2026 Multi-Endpoint Architecture.
    """
    def __init__(self, symbols=None, api_key=None, api_secret=None):
        self.symbols = symbols or []
        self.api_key = api_key
        self.api_secret = api_secret
        self.queue = asyncio.Queue()
        self.loop = None # Will be set in stream()
        self._running = False
        self.ws = None
        self.private_ws = None
        self.listen_key = None
        self._msg_count = 0
        self._raw_debug_count = {"public": 0, "private": 0}
        self._keep_alive_task = None
        self._public_task = None
        self._private_task = None

    @staticmethod
    def _normalize_symbol(symbol):
        """Convert CCXT symbols like BTC/USDT:USDT into Binance stream names."""
        base_symbol = symbol.split(':', 1)[0]
        return base_symbol.replace('/', '').lower()

    def _build_public_streams(self):
        streams = []
        for symbol in self.symbols:
            sym = self._normalize_symbol(symbol)
            streams.append(f"{sym}@markPrice")
            streams.append(f"{sym}@kline_1m")
            streams.append(f"{sym}@kline_1h")

        return streams

    def _build_public_ws_url(self):
        """
        Builds URL for Market Data streams. 
        Uses WS_MARKET_BASE for regular frequency data like klines and markPrice.
        """
        streams = self._build_public_streams()
        if not streams:
            raise ValueError("No websocket streams configured.")

        # Binance combined streams must use /stream?streams=a/b/c.
        return f"{WS_MARKET_BASE}/stream?streams={'/'.join(streams)}"

    def _build_ws_url(self):
        # Backward-compatible alias for older tests and diagnostics.
        return self._build_public_ws_url()

    def _build_private_ws_url(self):
        """
        Builds URL for Private User Data streams.
        Uses WS_PRIVATE_BASE as per March 2026 requirements.
        """
        if not self.listen_key:
            raise ValueError("No listenKey configured for private websocket.")
        listen_key = quote(self.listen_key, safe="")
        # In 2026 architecture, /private/ws is the dedicated path
        return f"{WS_PRIVATE_BASE}/ws?listenKey={listen_key}"

    def _enqueue(self, payload):
        if self.loop:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)

    def _handle_message(self, message, label="unknown"):
        try:
            self._msg_count += 1
            
            # [DIAGNOSTIC] Log ONLY private raw messages at DEBUG for initial troubleshooting
            if label == "private" and self._raw_debug_count.get(label, 0) < 5:
                logger.debug(f"🔐 Private WS Handshake Msg: {message[:180]}...")
                self._raw_debug_count[label] = self._raw_debug_count.get(label, 0) + 1

            data = json.loads(message)
            payload = data.get('data', data)

            if isinstance(payload, dict) and payload.get('result') is None and 'id' in payload:
                logger.debug(f"✅ WebSocket subscription acknowledged ({label}, id={payload['id']}).")
                return
            
            # [REDUCED NOISE] Silence all public diagnostics at INFO level
            if self._msg_count % 1000 == 1:
                logger.debug(f"📊 WS Flow Heartbeat (Total: {self._msg_count}) | Last Type: {payload.get('e')} | Src: {label}")

            if isinstance(payload, dict) and label == "private":
                event_type = payload.get('e')
                
                # Keep major private events at INFO level for user visibility
                if event_type in ['ORDER_TRADE_UPDATE', 'ACCOUNT_UPDATE', 'MARGIN_CALL', 'ORDER_TRADE_LITE']:
                    logger.info(f"🔐 Private WS Event: {event_type}")
                else:
                    # Elevate misc private events to INFO as well per user request
                    logger.info(f"🔐 Private WS Misc Event: {event_type}")

                if event_type == 'ORDER_TRADE_UPDATE':
                    o = payload['o']
                    order_logger.info(
                        f"🔔 [ORDER] {o['s']} | {o['S']} {o['o']} | Status: {o['X']} | "
                        f"Exec: {o['x']} | Qty: {o['z']}/{o['q']} | Price: {o.get('ap', o.get('L', '0'))} | ID: {o['i']}"
                    )
                elif event_type == 'ACCOUNT_UPDATE':
                    order_logger.info(f"💰 [ACCOUNT_UPDATE] Reason: {payload.get('a', {}).get('m')}")

            self._enqueue(payload)
        except Exception as e:
            logger.error(f"Error parsing message: {e}")

    def _on_message(self, ws, message):
        # Backward-compatible hook for tests or legacy websocket-client callers.
        self._handle_message(message)

    async def _get_listen_key(self):
        from src.config import CONFIG
        import ccxt.async_support as ccxt
        exchange = ccxt.binance({'apiKey': self.api_key or CONFIG.get("BINANCE_API_KEY"), 'secret': self.api_secret or CONFIG.get("BINANCE_SECRET"), 'options': {'defaultType': 'future'}})
        try:
            res = await exchange.fapiPrivatePostListenKey()
            await exchange.close()
            listen_key = res.get('listenKey')
            if listen_key:
                logger.info(f"🔑 User Data Stream listenKey active: {listen_key[:6]}***")
            return listen_key
        except Exception as e:
            logger.error(f"ListenKey Error: {e}")
            await exchange.close()
            return None

    async def _keep_alive_loop(self):
        from src.config import CONFIG
        import ccxt.async_support as ccxt

        while self._running:
            try:
                if not self.listen_key:
                    # Attempt to acquire or recover listen_key
                    self.listen_key = await self._get_listen_key()
                    if not self.listen_key:
                        await asyncio.sleep(60)
                        continue

                # Refresh every 30 minutes.
                # In 2026 architecture, listenKeys are valid for 60m, refresh extends it.
                await asyncio.sleep(30 * 60)
                
                # Check running status again after long sleep
                if not self._running or not self.listen_key:
                    continue

                exchange = ccxt.binance({
                    'apiKey': self.api_key or CONFIG.get("BINANCE_API_KEY"),
                    'secret': self.api_secret or CONFIG.get("BINANCE_SECRET"),
                    'options': {'defaultType': 'future'},
                })
                try:
                    await exchange.fapiPrivatePutListenKey({'listenKey': self.listen_key})
                    logger.info("🔑 Binance listenKey keep-alive refreshed.")
                except Exception as e:
                    # If key is invalid/expired (-1125), reset it to force re-acquisition
                    if "-1125" in str(e) or "This listenKey does not exist" in str(e):
                        logger.warning(f"⚠️ ListenKey {self.listen_key[:6]}*** expired or invalid. Resetting...")
                        self.listen_key = None
                        if self.private_ws:
                            await self.private_ws.close()
                            logger.info("🔄 Closed private WS to force reconnection with new key.")
                    else:
                        logger.error(f"ListenKey keep-alive error: {e}")
                finally:
                    await exchange.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Keep-alive loop encountered an unexpected error: {e}")
                await asyncio.sleep(60)

    async def _run_socket(self, url, label):
        display_url = url
        if label == "private" and self.listen_key:
            display_url = url.replace(self.listen_key, f"{self.listen_key[:6]}***")
        logger.info(f"🔗 Connecting {label} stream: {display_url[:180]}...")

        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=15) as ws:
                if label == "private":
                    self.private_ws = ws
                else:
                    self.ws = ws
                logger.info(f"✅ WebSocket Handshake Success ({label}).")
                self._enqueue({"e": "WS_RECONNECTED"})

                async for message in ws:
                    self._handle_message(message, label)
        finally:
            if label == "private":
                self.private_ws = None
            else:
                self.ws = None

    async def connect_and_run(self):
        # Backward-compatible public-stream runner for older tests and scripts.
        await self._run_socket(self._build_public_ws_url(), "public")

    async def _connection_loop(self, url_builder, label):
        backoff = 1
        while self._running:
            try:
                url = url_builder()
                await self._run_socket(url, label)
                backoff = 1
            except asyncio.CancelledError:
                break
            except ValueError as e:
                # Likely "No listenKey configured" - log as warning and wait
                logger.warning(f"🕒 {label} stream waiting for configuration: {e}")
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"❌ WebSocket connection error ({label}): {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def stream(self):
        self._running = True
        self.loop = asyncio.get_running_loop()
        
        if self.api_key:
            # Start keep-alive task first; it will acquire the key if missing
            self.listen_key = await self._get_listen_key()
            self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())

        self._public_task = asyncio.create_task(
            self._connection_loop(self._build_public_ws_url, "public")
        )

        if self.api_key:
            # Always start private task if we have API keys; it will wait for listen_key
            self._private_task = asyncio.create_task(
                self._connection_loop(self._build_private_ws_url, "private")
            )

        try:
            while self._running:
                try:
                    # Use a timeout to avoid hanging forever if no data comes
                    msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    yield msg
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    break
        finally:
            self.stop()

    def stop(self):
        self._running = False
        if self._keep_alive_task and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
        if self._public_task and not self._public_task.done():
            self._public_task.cancel()
        if self._private_task and not self._private_task.done():
            self._private_task.cancel()
        logger.info("Stopping WebSocket Manager...")
