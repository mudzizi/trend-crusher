import asyncio
import logging
import sys
from src.websocket_manager import BinanceWebSocketManager

# 로깅 설정 (내부 동작 확인용)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    stream=sys.stdout
)

async def main():
    # 1. 매니저 초기화 (심볼 하나만 테스트)
    symbols = ['BTC/USDT']
    manager = BinanceWebSocketManager(symbols=symbols)
    
    print(f"\n🚀 {symbols[0]} 실시간 가격 수신 테스트를 시작합니다...")
    
    count = 0
    try:
        # 2. 스트림 시작 및 데이터 수신 대기
        async for msg in manager.stream():
            # 실제 가격 데이터(markPriceUpdate)만 필터링
            if isinstance(msg, dict) and msg.get('e') == 'markPriceUpdate':
                symbol = msg.get('s')
                price = msg.get('p')
                count += 1
                print(f"✅ [수신 성공 {count}/3] {symbol} 실시간 가격: {price}")
            
            # 3개 받으면 종료
            if count >= 3:
                print("\n✨ 테스트 결과: 실제 데이터 수신이 완벽하게 확인되었습니다.")
                break
                
    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
    finally:
        manager.stop()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
