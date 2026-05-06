import asyncio
import logging
import sys
import os
import json
from src.websocket_manager import BinanceWebSocketManager
from src.config import CONFIG
import ccxt.async_support as ccxt

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("VerifyPrivateWS")

async def verify_private_stream():
    # 1. Initialize CCXT for order placement/cancellation
    api_key = CONFIG.get("BINANCE_API_KEY")
    api_secret = CONFIG.get("BINANCE_SECRET")
    
    if not api_key or not api_secret:
        logger.error("API Key or Secret missing in CONFIG. Cannot run private test.")
        return

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'defaultType': 'future'}
    })

    # 2. Initialize WebSocket Manager
    symbol = 'BTC/USDT'
    manager = BinanceWebSocketManager(symbols=[symbol], api_key=api_key, api_secret=api_secret)
    
    logger.info(f"🚀 Starting Private Stream test for {symbol}...")
    
    order_id = None
    received_new = False
    received_canceled = False

    async def stream_listener():
        nonlocal received_new, received_canceled
        async for msg in manager.stream():
            if isinstance(msg, dict) and msg.get('e') == 'ORDER_TRADE_UPDATE':
                order_data = msg.get('o', {})
                status = order_data.get('X')
                logger.info(f"🔔 [WS EVENT] Order Status: {status} | ID: {order_data.get('i')}")
                
                if status == 'NEW':
                    received_new = True
                elif status == 'CANCELED':
                    received_canceled = True
            
            if received_new and received_canceled:
                break

    # Start the listener task
    listener_task = asyncio.create_task(stream_listener())
    
    # Wait for WS to connect (handshake)
    await asyncio.sleep(5) 

    try:
        # 3. Place a probe order (Limit order far from market)
        logger.info("📡 Placing probe LIMIT BUY order at $10,000 (far from market)...")
        # Set amount to 0.01 BTC to ensure notional > 50 USDT (approx $800 at current prices)
        price = 10000.0
        amount = 0.01 
        
        order = await exchange.create_order(symbol, 'limit', 'buy', amount, price)
        order_id = order['id']
        logger.info(f"✅ Order Placed: {order_id}")

        # Wait for 'NEW' event
        for _ in range(10):
            if received_new: break
            await asyncio.sleep(1)

        if not received_new:
            logger.error("❌ Timed out waiting for 'NEW' order event.")
        
        # 4. Cancel the probe order
        logger.info(f"📡 Canceling order {order_id}...")
        await exchange.cancel_order(order_id, symbol)
        logger.info("✅ Cancel request sent.")

        # Wait for 'CANCELED' event
        for _ in range(10):
            if received_canceled: break
            await asyncio.sleep(1)

        if not received_canceled:
            logger.error("❌ Timed out waiting for 'CANCELED' order event.")
        else:
            logger.info("✨ SUCCESS: Both NEW and CANCELED events received via Private WebSocket!")

    except Exception as e:
        logger.error(f"❌ Error during test: {e}")
    finally:
        # Cleanup
        if order_id and not received_canceled:
            try:
                await exchange.cancel_order(order_id, symbol)
            except:
                pass
        
        manager.stop()
        await listener_task
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(verify_private_stream())
