import asyncio
import ccxt.async_support as ccxt
from src.config import CONFIG
from src.db_manager import DBManager
from src.telegram_utils import TelegramNotifier
from scripts.live_bot_async import SymbolBotAsync
from src.portfolio_manager_async import PortfolioManagerAsync
import pandas as pd

async def test_live_cycle():
    """
    실제 거래소에서 소액으로 주문-체결-SL 생성-청산 사이클을 검증합니다.
    """
    db, notifier = DBManager(), TelegramNotifier()
    exchange = getattr(ccxt, CONFIG["EXCHANGE"])({
        'apiKey': CONFIG["BINANCE_API_KEY"], 
        'secret': CONFIG["BINANCE_SECRET"], 
        'options': {'defaultType': 'future'}
    })
    pm = PortfolioManagerAsync(exchange, CONFIG)
    
    # 1. 테스트 대상 심볼 (소액 테스트용)
    symbol = CONFIG["SYMBOLS_LIST"][0]
    print(f"🧪 Starting Live Cycle Test for {symbol}...")
    
    try:
        await exchange.load_markets()
        bot = SymbolBotAsync(symbol, exchange, pm, notifier, db)
        await bot.initialize()
        
        # 2. 현재가 조회
        ticker = await exchange.fetch_ticker(symbol)
        last_price = ticker['last']
        print(f"💰 Current Price: {last_price}")

        # 3. 강제 진입 신호 생성 (현재가에서 0.1% 위에 Sniper 주문)
        # 시장가보다 살짝 높은 STOP_MARKET을 걸어 즉시 체결 유도
        target_price = last_price * 1.001 
        atr = last_price * 0.01 # 가상의 ATR
        
        print(f"🏹 Placing Sniper BUY at {target_price:.4f} with small qty...")
        
        # RISK를 최소로 하여 수량 계산
        bot.settings['RISK_PER_TRADE_PCT'] = 0.05 
        await bot.manage_sniper_ambush(1, target_price, atr)
        
        if bot.active_sniper_order_id:
            print(f"✅ Sniper Order Placed! ID: {bot.active_sniper_order_id}")
            print("⏳ Waiting for 30s to detect fill via polling or WS...")
            
            # 30초 동안 1초 주기로 체크
            for _ in range(30):
                await bot.check_sniper_fill()
                if bot.position != 0:
                    print(f"🎯 FILL DETECTED! Entry Price: {bot.entry_price}")
                    break
                await asyncio.sleep(1)
            
            if bot.position != 0:
                print(f"🛡️ SL Order ID: {bot.sl_order_id}")
                print("🏁 Test Step 1 Success: Order & Fill & SL working.")
                
                # 테스트 종료를 위해 즉시 청산 (선택 사항)
                print("🧹 Cleaning up: Closing position...")
                await bot.force_exit()
                print("✅ cleanup complete.")
            else:
                print("❌ Fill not detected within 30s. Cancelling...")
                await bot.cancel_sniper_ambush()
        else:
            print("❌ Failed to place sniper order.")

    except Exception as e:
        print(f"🚨 Test Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_live_cycle())
