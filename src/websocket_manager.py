import asyncio
import json
import logging
import time
import os
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

class BinanceWebSocketManager:
    """
    Pure Async WebSocket Manager for Binance Futures.
    Optimized for GCP/Cloud environments:
    1. Uses port 443 (Standard HTTPS) to bypass firewall blocks.
    2. Uses Combined Streams for maximum data reliability.
    3. Runs entirely within the asyncio loop (No background threads).
    """
    def __init__(self, symbols=None, api_key=None, api_secret=None, base_url="wss://fstream.binance.com/stream"):
        self.symbols = symbols
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.queue = asyncio.Queue()
        self._running = False
        self.listen_key = None
        self._keep_alive_task = None
        self._msg_debug_count = 0

    async def _get_listen_key(self):
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
        """Periodically extends the listenKey to prevent expiry."""
        if not self.api_key:
            return
            
        while self._running and self.listen_key:
            await asyncio.sleep(1800) # 30 minutes
            from src.config import CONFIG
            import ccxt.async_support as ccxt
            exchange = ccxt.binance({
                'apiKey': self.api_key or CONFIG.get("BINANCE_API_KEY"),
                'secret': self.api_secret or CONFIG.get("BINANCE_SECRET"),
                'options': {'defaultType': 'future'}
            })
            try:
                await exchange.fapiPrivatePutListenKey()
                logger.info("📡 listenKey keep-alive successful.")
            except Exception as e:
                logger.warning(f"⚠️ listenKey keep-alive failed: {e}. Re-fetching...")
                self.listen_key = await self._get_listen_key()
                # If re-fetching happens, the main loop will handle reconnection if needed
            finally:
                await exchange.close()

    async def connect_and_run(self):
        """Main connection loop with automatic reconnection."""
        self._running = True
        
        # 1. Start Keep-alive task if API keys are present
        if self.api_key and not self._keep_alive_task:
            self.listen_key = await self._get_listen_key()
            if self.listen_key:
                self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())

        while self._running:
            try:
                # 2. Construct Combined Stream URL
                # Standard streams
                streams = []
                for symbol in self.symbols:
                    s = symbol.replace('/', '').lower()
                    streams.append(f"{s}@markPrice")
                    streams.append(f"{s}@kline_1m")
                    streams.append(f"{s}@kline_1h")
                
                # Add private stream if available
                if self.listen_key:
                    streams.append(self.listen_key)
                
                url = f"{self.base_url}?streams={'/'.join(streams)}"
                logger.info(f"🔗 Connecting to Combined Stream: {url[:80]}...")

                # 3. Connect via port 443 (implicitly handled by wss://)
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("✅ WebSocket Connected (Port 443/Combined)")
                    self.queue.put_nowait({"e": "WS_RECONNECTED"})
                    
                    async for message in ws:
                        if not self._running: break
                        
                        # Debug: Log first 10 raw messages
                        if self._msg_debug_count < 10:
                            logger.info(f"📥 Raw WS Message: {message[:100]}...")
                            self._msg_debug_count += 1

                        data = json.loads(message)
                        # Normalize Combined Stream format (Binance wraps data in 'data' field)
                        payload = data.get('data', data)
                        
                        # [CRITICAL] Log Order Updates
                        if isinstance(payload, dict) and payload.get('e') == 'ORDER_TRADE_UPDATE':
                            o = payload['o']
                            order_logger.info(f"🔔 [ORDER] {o['s']} | {o['X']} | ID: {o['i']} | Price: {o['ap']}")

                        self.queue.put_nowait(payload)

            except Exception as e:
                if self._running:
                    import traceback
                    logger.error(f"❌ WS Connection Error: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(5)

    async def stream(self):
        """Interface for the main bot loop."""
        self._running = True
        # Ensure the connection runner is started only once
        if not hasattr(self, '_conn_task') or self._conn_task.done():
            self._conn_task = asyncio.create_task(self.connect_and_run())
            # Give it a tiny head start
            await asyncio.sleep(0.1)
        
        while self._running or not self.queue.empty():
            try:
                # Use a small timeout to allow checking self._running
                msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                yield msg
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Error in stream generator: {e}")
                break

    def stop(self):
        self._running = False
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
        logger.info("Stopping WebSocket Manager...")
