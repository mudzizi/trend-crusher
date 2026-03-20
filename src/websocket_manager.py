import asyncio
import json
import websockets
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class BinanceWebSocketManager:
    """
    Manages WebSocket connections to Binance Futures streams.
    Supports multiple symbols and automatic reconnection.
    """
    def __init__(self, symbols, base_url="wss://fstream.binance.com/ws"):
        self.symbols = [s.replace('/', '').lower() for s in symbols]
        self.base_url = base_url
        self.streams = []
        for s in self.symbols:
            self.streams.append(f"{s}@kline_1h")
            self.streams.append(f"{s}@kline_1m")
            self.streams.append(f"{s}@markPrice")
        
        self.url = f"{self.base_url}/{'/'.join(self.streams)}"
        self.queue = asyncio.Queue()
        self._running = False

    async def connect(self):
        self._running = True
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        while self._running:
            try:
                logger.info(f"Connecting to Binance WebSocket: {self.url}")
                async with websockets.connect(self.url, ssl=ssl_context) as ws:
                    logger.info("✅ WebSocket Connected Successfully")
                    while self._running:
                        message = await ws.recv()
                        data = json.loads(message)
                        await self.queue.put(data)
            except Exception as e:
                logger.error(f"❌ WebSocket Connection Error: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

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
