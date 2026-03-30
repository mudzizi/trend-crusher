import asyncio
import json
import websockets
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class BinanceWebSocketManager:
    """
    Manages WebSocket connections to Binance Futures streams.
    Supports multiple symbols, public streams, and private User Data Stream.
    """
    def __init__(self, symbols=None, exchange=None, base_url="wss://fstream.binance.com/ws"):
        self.symbols = symbols
        self.exchange = exchange
        self.base_url = base_url
        self.queue = asyncio.Queue()
        self._running = False
        self.listen_key = None
        
        # Initial URL construction (Public streams only)
        self.url = self._construct_url(symbols, None)

    def _construct_url(self, symbols, listen_key):
        """Helper to construct the aggregate WebSocket URL."""
        streams = []
        if symbols:
            formatted_symbols = [s.replace('/', '').lower() for s in symbols]
            for s in formatted_symbols:
                streams.append(f"{s}@kline_1h")
                streams.append(f"{s}@kline_1m")
                streams.append(f"{s}@markPrice")
        
        if listen_key:
            streams.append(listen_key)
            
        if not streams:
            return None
            
        return f"{self.base_url}/{'/'.join(streams)}"

    async def _get_listen_key(self):
        """Fetches a new listenKey from Binance for private user data stream."""
        if not self.exchange: return None
        try:
            response = await self.exchange.fapiPrivatePostListenKey()
            return response.get('listenKey')
        except Exception as e:
            logger.error(f"Failed to fetch listenKey: {e}")
            return None

    async def _keep_alive_listen_key(self):
        """Pings the listenKey every 30 minutes to keep it active."""
        while self._running and self.listen_key:
            await asyncio.sleep(1800) # 30 minutes
            try:
                await self.exchange.fapiPrivatePutListenKey()
                logger.info("📡 listenKey keep-alive ping sent.")
            except Exception as e:
                logger.warning(f"listenKey keep-alive failed: {e}")

    async def connect(self):
        self._running = True
        
        # 1. Private Stream setup if exchange provided
        if self.exchange:
            self.listen_key = await self._get_listen_key()
            if self.listen_key:
                self.url = self._construct_url(self.symbols, self.listen_key)
                asyncio.create_task(self._keep_alive_listen_key())
        
        if not self.url:
            raise ValueError("No symbols or listenKey available for WebSocket.")

        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        reconnect_delay = 5
        while self._running:
            try:
                logger.info(f"Connecting to WebSocket: {self.url.split('/')[-1][:10]}...")
                async with websockets.connect(self.url, ssl=ssl_context, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("✅ WebSocket Connected Successfully")
                    reconnect_delay = 5
                    while self._running:
                        message = await ws.recv()
                        data = json.loads(message)
                        await self.queue.put(data)
            except Exception as e:
                if self._running:
                    logger.error(f"❌ WebSocket Error: {e}. Retrying in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 60)

    async def get_next_message(self):
        """Retrieves the next message from the queue."""
        return await self.queue.get()

    async def stream(self):
        """
        Async generator that yields messages from the WebSocket.
        Starts the connection task if not already running.
        """
        if not self._running:
            asyncio.create_task(self.connect())
            
        while True:
            yield await self.queue.get()

    def stop(self):
        self._running = False
        logger.info("Stopping WebSocket Manager...")
