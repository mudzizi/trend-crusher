import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync
import asyncio
import ccxt

@pytest.fixture
def mock_bot():
    mock_exchange = MagicMock()
    # Mocking retry_api_call dependency
    mock_exchange.fetch_ohlcv = AsyncMock()
    
    mock_pm = MagicMock()
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    
    bot = SymbolBotAsync("ETH/USDC", mock_exchange, mock_pm, mock_notifier, mock_db)
    # Mock settings
    bot.settings = {
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "DONCHIAN_PERIOD": 20,
        "ATR_PERIOD": 14,
        "AVG_VOL_PERIOD": 20,
        "VOL_MULTIPLIER": 1.5,
        "ADX_FILTER_LEVEL": 20,
        "EMA_TREND_PERIOD": 100,
        "INITIAL_SL_ATR": 2.0,
        "DRY_RUN": False
    }
    return bot

@pytest.mark.asyncio
async def test_fetch_ohlcv_retries_on_failure(mock_bot):
    """fetch_ohlcv가 실패할 때 retry_api_call이 정상적으로 작동하는지 확인"""
    # 1, 2회차는 에러 발생, 3회차에 성공하는 시나리오
    mock_ohlcv_data = [[1600000000000, 1.0, 1.1, 0.9, 1.05, 100]]
    mock_bot.exchange.fetch_ohlcv.side_effect = [
        ccxt.NetworkError("First failure"),
        ccxt.NetworkError("Second failure"),
        mock_ohlcv_data
    ]
    
    # fetch_ohlcv 호출 (내부적으로 retry_api_call 사용)
    df = await mock_bot.fetch_ohlcv("1h")
    
    # 결과 확인
    assert not df.empty
    assert len(df) == 1
    assert mock_bot.exchange.fetch_ohlcv.call_count == 3
    print("\n✅ Retry logic verified: Succeeds after 2 failures.")

@pytest.mark.asyncio
async def test_initialize_resilience(mock_bot):
    """초기화 도중 네트워크 에러가 발생해도 로그를 남기고 raise하는지 확인"""
    mock_bot.exchange.fetch_ohlcv.side_effect = ccxt.NetworkError("Startup Failure")
    
    with pytest.raises(ccxt.NetworkError):
        await mock_bot.initialize()
    
    assert mock_bot.exchange.fetch_ohlcv.call_count >= 1 # At least tried once (plus retries)
    print("✅ Startup resilience verified: Handles initial connection failure.")

@pytest.mark.asyncio
async def test_on_kline_update_error_handling(mock_bot):
    """캔들 종료 시 업데이트 실패해도 봇이 죽지 않는지 확인"""
    mock_bot.exchange.fetch_ohlcv.side_effect = Exception("Random API Error")
    
    # Initialize buffers to avoid early return
    now = pd.Timestamp.now().floor('h')
    mock_bot.ohlcv_1h = pd.DataFrame([[now, 1, 1, 1, 1, 1]], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    mock_bot.ohlcv_4h = mock_bot.ohlcv_1h.copy()

    # 이 호출은 에러를 내부적으로 catch하고 로그만 남겨야 함 (봇이 죽으면 안 됨)
    # 신규 캔들이 시작되는 시나리오 (t > last_ts) 여야 fetch_ohlcv를 호출함
    new_ts = now + pd.Timedelta(hours=1)
    kline_msg = {
        't': int(new_ts.timestamp() * 1000),
        'o': '1', 'h': '1', 'l': '1', 'c': '1', 'v': '1',
        'x': True, 
        'i': '1h'
    }
    
    await mock_bot.on_kline_update("1h", kline_msg)
    
    # 여기까지 도달하면 성공
    assert mock_bot.exchange.fetch_ohlcv.called
    print("✅ Kline update resilience verified: No crash on API error.")

@pytest.mark.asyncio
async def test_command_flushing_on_startup():
    """봇 시작 시 이전 텔레그램 명령어를 무시(Flush)하는지 확인"""
    from scripts.live_bot_async import handle_commands
    
    # handle_commands 내부의 try-except Exception을 우회하기 위해 BaseException 사용
    class StopLoop(BaseException): pass
    
    mock_notifier = MagicMock()
    # Mock some old messages sitting on the server
    mock_notifier.get_updates.side_effect = [
        {"ok": True, "result": [{"update_id": 100, "message": {"text": "/close_all"}}]}, # First call (flush)
        {"ok": True, "result": []}, # Second call (wait)
        StopLoop() # Third call to break the infinite loop
    ]
    
    mock_pm = MagicMock()
    mock_bots = {}
    
    with patch('src.optimizer_engine.OptimizerEngine', MagicMock()), \
         patch('os._exit', MagicMock()), \
         patch('asyncio.sleep', AsyncMock()):
        try:
            await handle_commands(mock_bots, mock_notifier)
        except StopLoop:
            pass # Expected break
            
    # Check that the first get_updates was called with offset=None (flush)
    # And subsequent calls used offset=101
    assert mock_notifier.get_updates.call_count >= 2
    mock_notifier.get_updates.assert_any_call(None)
    mock_notifier.get_updates.assert_any_call(101)
    print("✅ Command flushing verified: Old commands are skipped on startup.")
