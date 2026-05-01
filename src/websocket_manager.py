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

PUBLIC_WS_BASE_URL = "wss://fstream.binancefuture.com"
PRIVATE_WS_BASE_URL = "wss://fstream.binance.com"

class BinanceWebSocketManager:
    """
    Async Binance Futures WebSocket manager.
    Uses combined streams so market data and user-data events share one queue.
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
        streams = self._build_public_streams()
        if not streams:
            raise ValueError("No websocket streams configured.")

        # Binance combined streams must use /stream?streams=a/b/c.
        # /ws/<stream> is only valid for a single raw stream.
        return f"{PUBLIC_WS_BASE_URL}/stream?streams={'/'.join(streams)}"

    def _build_ws_url(self):
        # Backward-compatible alias for older tests and diagnostics.
        return self._build_public_ws_url()

    def _build_private_ws_url(self):
        if not self.listen_key:
            raise ValueError("No listenKey configured for private websocket.")
        listen_key = quote(self.listen_key, safe="")
        events = quote("ORDER_TRADE_UPDATE", safe="")
        return f"{PRIVATE_WS_BASE_URL}/private/ws?listenKey={listen_key}&events={events}"

    def _enqueue(self, payload):
        if self.loop:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)

    def _handle_message(self, message, label="unknown"):
        try:
            self._msg_count += 1
            if self._raw_debug_count.get(label, 0) < 5:
                logger.info(f"📥 Raw WS Message ({label}): {message[:180]}...")
                self._raw_debug_count[label] = self._raw_debug_count.get(label, 0) + 1

            data = json.loads(message)
            payload = data.get('data', data)

            if isinstance(payload, dict) and payload.get('result') is None and 'id' in payload:
                logger.info(f"✅ WebSocket subscription acknowledged ({label}, id={payload['id']}).")
                return
            
            # [DIAGNOSTIC] Log every 50th message to prove life without flooding
            if self._msg_count % 50 == 1:
                logger.info(f"📊 WS Data Flowing... (Msg #{self._msg_count}) Last Type: {payload.get('e')} Source: {label}")

            if isinstance(payload, dict) and label == "private":
                logger.info(f"🔐 Private WS Event: {payload.get('e')}")

            if isinstance(payload, dict):
                event_type = payload.get('e')
                if event_type == 'ORDER_TRADE_UPDATE':
                    o = payload['o']
                    order_logger.info(
                        f"🔔 [ORDER] {o['s']} | {o['S']} {o['o']} | Status: {o['X']} | "
                        f"Exec: {o['x']} | Qty: {o['z']}/{o['q']} | Price: {o.get('ap', o.get('L', '0'))} | ID: {o['i']}"
                    )
                elif event_type == 'TRADE_LITE':
                    order_logger.info(
                        f"⚡ [TRADE_LITE] {payload.get('s')} | Side: {payload.get('S')} | "
                        f"Qty: {payload.get('q')} | Price: {payload.get('p')} | Order: {payload.get('i')}"
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

        while self._running and self.listen_key:
            try:
                await asyncio.sleep(30 * 60)
                exchange = ccxt.binance({
                    'apiKey': self.api_key or CONFIG.get("BINANCE_API_KEY"),
                    'secret': self.api_secret or CONFIG.get("BINANCE_SECRET"),
                    'options': {'defaultType': 'future'},
                })
                try:
                    await exchange.fapiPrivatePutListenKey({'listenKey': self.listen_key})
                    logger.info("🔑 Binance listenKey keep-alive refreshed.")
                finally:
                    await exchange.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ListenKey keep-alive error: {e}")

    async def _run_socket(self, url, label):
        display_url = url
        if label == "private" and self.listen_key:
            display_url = url.replace(self.listen_key, f"{self.listen_key[:6]}***")
        logger.info(f"🔗 Connecting {label} stream: {display_url[:180]}...")

        async with websockets.connect(url, ping_interval=20, ping_timeout=15) as ws:
            if label == "private":
                self.private_ws = ws
            else:
                self.ws = ws
            logger.info(f"✅ WebSocket Handshake Success ({label}).")
            self._enqueue({"e": "WS_RECONNECTED"})

            async for message in ws:
                self._handle_message(message, label)

    async def connect_and_run(self):
        # Backward-compatible public-stream runner for older tests and scripts.
        await self._run_socket(self._build_public_ws_url(), "public")

    async def _connection_loop(self, url_builder, label):
        backoff = 1
        while self._running:
            try:
                await self._run_socket(url_builder(), label)
                backoff = 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ WebSocket connection error: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def stream(self):
        self._running = True
        self.loop = asyncio.get_running_loop()
        
        if self.api_key:
            self.listen_key = await self._get_listen_key()
            if self.listen_key:
                self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())

        self._public_task = asyncio.create_task(
            self._connection_loop(self._build_public_ws_url, "public")
        )

        if self.listen_key:
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
