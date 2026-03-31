import asyncio
import json
import logging
import sys
import os
from datetime import datetime
from src.config import CONFIG
from src.websocket_manager import BinanceWebSocketManager

# --- Logging Setup (Minimal for stdout clarity) ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("EventMonitor")

async def main():
    """
    WebSocket Event Monitor: Same structure as live_bot_async.py
    Used for debugging and verifying real-time data flows.
    """
    logger.info("🔍 Starting WebSocket Event Monitor (v12.9.1)...")
    logger.info(f"📡 Watching Symbols: {CONFIG['SYMBOLS_LIST']}")
    
    # Initialize using the same manager as live_bot_async
    ws_manager = BinanceWebSocketManager(
        symbols=CONFIG["SYMBOLS_LIST"], 
        api_key=CONFIG["BINANCE_API_KEY"], 
        api_secret=CONFIG["BINANCE_SECRET"]
    )

    try:
        # Start the stream (this matches the live_bot_async structure)
        async for msg in ws_manager.stream():
            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # 1. Handle special internal events
            if isinstance(msg, dict) and msg.get('e') == 'WS_RECONNECTED':
                print(f"\n[{now}] 🔄 [RECONNECT EVENT] WebSocket session refreshed.\n" + "-"*50)
                continue

            # 2. Extract payload (handle combined stream wrapper)
            payload = msg.get('data', msg) if isinstance(msg, dict) else msg
            
            # 3. Categorize and Print
            if isinstance(payload, dict) and 'e' in payload:
                e_type = payload['e']
                symbol = payload.get('s', 'UNKNOWN')
                
                if e_type == 'ORDER_TRADE_UPDATE':
                    print(f"\n[{now}] 🔔 [ORDER_UPDATE] Symbol: {symbol}")
                    print(json.dumps(payload['o'], indent=4))
                    print("-" * 50)
                
                elif e_type == 'markPriceUpdate':
                    print(f"[{now}] 📈 [MARK_PRICE] {symbol}: {payload['p']}")
                
                elif e_type == 'kline':
                    k = payload['k']
                    if k['x']: # Only print closed candles to avoid flood, or remove this if you want every tick
                        print(f"[{now}] 🕯️ [KLINE_CLOSED] {symbol} {k['i']}: Close={k['c']}")
                
                elif e_type == 'ACCOUNT_UPDATE':
                    print(f"\n[{now}] 💰 [ACCOUNT_UPDATE]")
                    print(json.dumps(payload['a'], indent=4))
                    print("-" * 50)
                
                else:
                    # Other events (e.g. continuous_kline, etc.)
                    print(f"[{now}] 📦 [OTHER:{e_type}] {symbol}")
            else:
                # Raw output for unexpected formats
                print(f"[{now}] 📥 [RAW_MESSAGE] {msg}")

    except asyncio.CancelledError:
        logger.info("Monitor stopped by user.")
    except Exception as e:
        logger.error(f"Monitor crash: {e}")
    finally:
        ws_manager.stop()
        logger.info("📡 WebSocket connection closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
