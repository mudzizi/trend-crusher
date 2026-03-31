import asyncio
import json
import logging
import time
import os
from binance.websocket.um_futures.websocket_client import UMFuturesWebsocketClient

# --- Account-wide Order Logger Setup ---
os.makedirs("log", exist_ok=True)
order_logger = logging.getLogger("AccountOrders")
order_logger.setLevel(logging.INFO)
if not order_logger.handlers:
    fh = logging.FileHandler("log/account_orders.log")
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    order_logger.addHandler(fh)

logger = logging.getLogger(__name__)

class BinanceWebSocketManager:
    """
    Advanced WebSocket Manager for Binance Futures.
    Handles 24h reconnection, Ping/Pong, and resilient ListenKey management.
    """
    def __init__(self, symbols=None, api_key=None, api_secret=None, base_url="wss://fstream.binance.com"):
        self.symbols = symbols
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.queue = asyncio.Queue()
        self.loop = asyncio.get_event_loop()
        self.ws_client = None
        self._running = False
        self.listen_key = None
        self.last_reconnect_ts = 0

    def _on_message(self, _, message):
        """Callback for all incoming WebSocket messages."""
        if not self._running:
            return
            
        try:
            data = json.loads(message)
            
            # [CRITICAL] Log EVERY order update for the entire account
            payload = data.get('data', data) if isinstance(data, dict) else data
            if isinstance(payload, dict) and payload.get('e') == 'ORDER_TRADE_UPDATE':
                o = payload['o']
                log_msg = f"🔔 [ORDER] {o['s']} | {o['S']} {o['o']} | Status: {o['X']} | Qty: {o['z']}/{o['q']} | Price: {o['ap'] or o['L']} | ID: {o['i']}"
                order_logger.info(log_msg)
                logger.info(f"Account-wide Order Event: {o['s']} {o['X']}")

            # Safely put the message into the asyncio Queue
            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self.queue.put_nowait, data)
            else:
                logger.debug("Skipping message because event loop is not running.")
        except Exception as e:
            if self._running:
                logger.error(f"Error processing WS message: {e}")

    def _on_error(self, _, error):
        logger.error(f"❌ WebSocket Client Error: {error}")
        # Re-trigger reconnection logic if needed

    def _on_open(self, _):
        logger.info("✅ WebSocket Connection Opened/Re-opened")
        self.last_reconnect_ts = time.time()
        # Signal a reconnection event to the queue so the bot can sync orders
        self.loop.call_soon_threadsafe(self.queue.put_nowait, {"e": "WS_RECONNECTED"})

    async def connect(self):
        """Initializes the UMWebsocketClient and starts streams."""
        self._running = True
        
        # 1. Initialize official UM Futures WebSocket Client
        # The library handles PING/PONG and 24h reconnection internally.
        self.ws_client = UMFuturesWebsocketClient(
            on_message=self._on_message,
            on_error=self._on_error,
            on_open=self._on_open,
            stream_url=self.base_url
        )
        
        # 2. Subscribe to Public Streams
        if self.symbols:
            for symbol in self.symbols:
                s = symbol.replace('/', '').lower()
                self.ws_client.kline(symbol=s, interval="1h")
                self.ws_client.kline(symbol=s, interval="1m")
                self.ws_client.mark_price(symbol=s, speed=1)
            logger.info(f"📡 Subscribed to Public Streams for {len(self.symbols)} symbols")

        # 3. Subscribe to Private User Data Stream
        if self.api_key:
            await self._refresh_user_data_stream()

    async def _refresh_user_data_stream(self):
        """Fetches a new listenKey and starts/updates the user data stream."""
        old_key = self.listen_key
        self.listen_key = await self._get_new_listen_key()
        
        if self.listen_key:
            if old_key:
                # If we had an old key, we might need to stop the old stream (library might handle this but better safe)
                pass 
            self.ws_client.user_data(listen_key=self.listen_key, id=1)
            logger.info(f"🔑 User Data Stream Active with Key: {self.listen_key[:5]}***")
            
            # (Re)start the keep-alive task
            if hasattr(self, '_keep_alive_task') and not self._keep_alive_task.done():
                self._keep_alive_task.cancel()
            self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())

    async def _get_new_listen_key(self):
        """Fetches a fresh listenKey using ccxt."""
        from src.config import CONFIG
        import ccxt.async_support as ccxt
        exchange = ccxt.binance({
            'apiKey': self.api_key or CONFIG.get("BINANCE_API_KEY"),
            'secret': self.api_secret or CONFIG.get("BINANCE_SECRET"),
            'options': {'defaultType': 'future'}
        })
        try:
            response = await exchange.fapiPrivatePostListenKey()
            await exchange.close()
            return response.get('listenKey')
        except Exception as e:
            logger.error(f"Failed to fetch new listenKey: {e}")
            await exchange.close()
            return None

    async def _keep_alive_loop(self):
        """Resilient keep-alive loop. If pings fail, it re-issues the key."""
        from src.config import CONFIG
        import ccxt.async_support as ccxt
        
        while self._running and self.listen_key:
            await asyncio.sleep(1800) # Every 30 mins (safe margin for 60m expiry)
            
            exchange = ccxt.binance({
                'apiKey': self.api_key or CONFIG.get("BINANCE_API_KEY"),
                'secret': self.api_secret or CONFIG.get("BINANCE_SECRET"),
                'options': {'defaultType': 'future'}
            })
            try:
                # Try to extend existing key
                await exchange.fapiPrivatePutListenKey()
                logger.info("📡 listenKey keep-alive successful.")
            except Exception as e:
                logger.warning(f"⚠️ listenKey keep-alive failed: {e}. Re-issuing key...")
                # If extension fails (key might have expired or been revoked), get a new one
                await self._refresh_user_data_stream()
                break # Exit current loop as _refresh_user_data_stream starts a new one
            finally:
                await exchange.close()

    async def stream(self):
        if not self._running:
            await self.connect()
            
        while self._running:
            yield await self.queue.get()

    def stop(self):
        self._running = False
        if hasattr(self, '_keep_alive_task'):
            self._keep_alive_task.cancel()
        if self.ws_client:
            self.ws_client.stop()
        logger.info("Stopping WebSocket Manager...")
