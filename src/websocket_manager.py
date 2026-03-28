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
    def __init__(self, symbols=None, listen_key=None, base_url="wss://fstream.binance.com/ws"):
        self.base_url = base_url
        self.queue = asyncio.Queue()
        self._running = False
        
        if listen_key:
            # User Data Stream URL
            self.url = f"{self.base_url}/{listen_key}"
        elif symbols:
            # Public Streams URL
            self.symbols = [s.replace('/', '').lower() for s in symbols]
            streams = []
            for s in self.symbols:
                streams.append(f"{s}@kline_1h")
                streams.append(f"{s}@kline_1m")
                streams.append(f"{s}@markPrice")
            self.url = f"{self.base_url}/{'/'.join(streams)}"
        else:
            raise ValueError("Either symbols or listen_key must be provided.")

    async def connect(self):
        self._running = True
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        reconnect_delay = 5
        while self._running:
            try:
                # Log only first 10 chars of URL to protect listenKey
                logger.info(f"Connecting to WebSocket: {self.url.split('/')[-1][:10]}...")
                async with websockets.connect(self.url, ssl=ssl_context, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("✅ WebSocket Connected Successfully")
                    reconnect_delay = 5 # Reset delay on success
                    while self._running:
                        message = await ws.recv()
                        data = json.loads(message)
                        await self.queue.put(data)
            except Exception as e:
                if self._running:
                    logger.error(f"❌ WebSocket Error: {e}. Retrying in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 60) # Exponential backoff

    async def get_next_message(self):
        """Retrieves the next message from the queue."""
        return await self.queue.get()

    def stop(self):
        self._running = False
        logger.info("Stopping WebSocket Manager...")

if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    async def test():
        manager = BinanceWebSocketManager(["BTC/USDT", "ETH/USDT"])
        asyncio.create_task(manager.connect())
        while True:
            msg = await manager.get_next_message()
            print(f"Received: {msg.get('e')} for {msg.get('s')}")
    
    asyncio.run(test())
