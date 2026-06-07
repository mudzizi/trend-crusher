import asyncio
import logging
import pandas as pd

logger = logging.getLogger("ExchangeAdapter")

class ExchangeAdapter:
    """
    Adapter class for exchange operations using CCXT.
    Capsules the retry logic and raw API call mappings.
    """
    def __init__(self, exchange, symbol, dry_run=False):
        self.exchange = exchange
        self.symbol = symbol
        self.dry_run = dry_run
        self.logger = logging.getLogger(f"Adapter-{symbol.split('/')[0]}")

    async def retry_api_call(self, func, *args, max_retries=3, delay=2, **kwargs):
        for i in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if i == max_retries - 1:
                    raise e
                self.logger.warning(f"⚠️ API Error: {e}. Retrying {i+1}/{max_retries}...")
                await asyncio.sleep(delay * (i + 1))

    async def fetch_ohlcv(self, tf, limit=1000):
        ohlcv = await self.retry_api_call(self.exchange.fetch_ohlcv, self.symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def fetch_order(self, order_id):
        return await self.retry_api_call(self.exchange.fetch_order, order_id, self.symbol)

    async def fetch_trigger_order(self, order_id):
        return await self.retry_api_call(self.exchange.fetch_order, order_id, self.symbol, params={'trigger': True})

    async def cancel_trigger_order(self, order_id):
        return await self.retry_api_call(self.exchange.cancel_order, order_id, self.symbol, params={'trigger': True})

    async def create_reduce_only_market_order(self, side, amount):
        return await self.retry_api_call(self.exchange.create_order, self.symbol, 'market', side, amount, None, params={'reduceOnly': True})

    async def get_all_open_orders(self):
        if self.dry_run and not ('Mock' in self.exchange.__class__.__name__ or 'mock' in str(type(self.exchange)).lower()):
            return []
        try:
            limit_orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol)
            self.logger.info(f"🔍 [{self.symbol}] Fetched standard open orders: {len(limit_orders)}")
        except Exception as e:
            self.logger.error(f"❌ [{self.symbol}] Error fetching limit orders: {e}")
            limit_orders = []
        try:
            stop_orders = await self.retry_api_call(self.exchange.fetch_open_orders, self.symbol, params={'stop': True})
            self.logger.info(f"🔍 [{self.symbol}] Fetched stop/trigger open orders: {len(stop_orders)}")
        except Exception as e:
            self.logger.error(f"❌ [{self.symbol}] Error fetching stop orders: {e}")
            stop_orders = []
        combined = {o['id']: o for o in limit_orders + stop_orders}
        return list(combined.values())

    async def fetch_positions(self):
        return await self.retry_api_call(self.exchange.fetch_positions, [self.symbol])

    async def cancel_all_orders(self):
        if self.dry_run and not ('Mock' in self.exchange.__class__.__name__ or 'mock' in str(type(self.exchange)).lower()):
            return
        await self.retry_api_call(self.exchange.cancel_all_orders, self.symbol)

    async def create_order(self, order_type, side, amount, price=None, params=None):
        params = params or {}
        return await self.retry_api_call(self.exchange.create_order, self.symbol, order_type, side, amount, price, params)

    async def create_market_order(self, side, amount):
        return await self.retry_api_call(self.exchange.create_market_order, self.symbol, side, amount)
