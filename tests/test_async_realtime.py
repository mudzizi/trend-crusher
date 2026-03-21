import pytest
import pandas as pd
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync

@pytest.fixture
def mock_bot():
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    settings = {
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "DONCHIAN_PERIOD": 20,
        "ATR_PERIOD": 14,
        "AVG_VOL_PERIOD": 20,
        "VOL_MULTIPLIER": 1.5,
        "ADX_FILTER_LEVEL": 25,
        "EMA_TREND_PERIOD": 200,
        "DRY_RUN": True
    }
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings = settings
    
    # Initialize mock OHLCV buffers
    now = pd.Timestamp.now().floor('h')
    data = []
    for i in range(100):
        data.append([now - pd.Timedelta(hours=100-i), 50000, 51000, 49000, 50500, 1000])
    
    bot.ohlcv_1h = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    bot.ohlcv_4h = bot.ohlcv_1h.copy() # Simplified for test
    
    return bot

@pytest.mark.asyncio
async def test_on_kline_update_realtime_modification(mock_bot):
    # 시나리오: 동일한 타임스탬프의 미확정 봉(x=False)이 들어왔을 때 
    # 기존 데이터프레임의 마지막 행이 업데이트되는지 확인
    
    last_ts = mock_bot.ohlcv_1h.iloc[-1]['timestamp']
    kline_msg = {
        't': int(last_ts.timestamp() * 1000),
        'o': '50500',
        'h': '52000', # High updated
        'l': '50000',
        'c': '51500', # Close updated
        'v': '1500',  # Volume updated
        'x': False    # NOT closed
    }
    
    # Mock check_entry/exit to avoid full strategy execution in this unit test
    mock_bot.check_entry = AsyncMock()
    mock_bot.check_exit = AsyncMock()
    
    await mock_bot.on_kline_update("1h", kline_msg)
    
    # 검증: 데이터프레임 길이는 그대로여야 함
    assert len(mock_bot.ohlcv_1h) == 100
    
    # 검증: 마지막 행의 값이 업데이트되었어야 함
    updated_row = mock_bot.ohlcv_1h.iloc[-1]
    assert updated_row['high'] == 52000.0
    assert updated_row['close'] == 51500.0
    assert updated_row['volume'] == 1500.0
    assert mock_bot.last_price == 51500.0
    
    # 검증: 실시간 트리거가 호출되었는지 확인
    mock_bot.check_entry.assert_called_once()

@pytest.mark.asyncio
async def test_on_kline_update_new_candle_sync(mock_bot):
    # 시나리오: 새로운 타임스탬프의 봉이 들어왔을 때 (새로운 시간대 시작)
    # fetch_ohlcv를 호출하여 버퍼를 동기화하는지 확인
    
    last_ts = mock_bot.ohlcv_1h.iloc[-1]['timestamp']
    new_ts = last_ts + pd.Timedelta(hours=1)
    
    kline_msg = {
        't': int(new_ts.timestamp() * 1000),
        'o': '51500',
        'h': '51600',
        'l': '51400',
        'c': '51550',
        'v': '100',
        'x': False
    }
    
    # fetch_ohlcv를 모킹하여 호출 여부 확인
    mock_bot.fetch_ohlcv = AsyncMock(return_value=mock_bot.ohlcv_1h)
    
    await mock_bot.on_kline_update("1h", kline_msg)
    
    # 검증: 새로운 캔들이 감지되어 fetch_ohlcv가 호출되었어야 함
    mock_bot.fetch_ohlcv.assert_called_with("1h")

@pytest.mark.asyncio
async def test_on_kline_update_ignore_irrelevant_tf(mock_bot):
    # 시나리오: 설정에 없는 '1m' 타임프레임 데이터가 들어왔을 때 무시해야 함
    mock_bot.fetch_ohlcv = AsyncMock()
    mock_bot.check_entry = AsyncMock()
    
    kline_msg = {
        't': 1600000000000,
        'o': '1', 'h': '1', 'l': '1', 'c': '1', 'v': '1',
        'x': True, 
        'i': '1m' # Irrelevant timeframe
    }
    
    await mock_bot.on_kline_update("1m", kline_msg)
    
    # 검증: fetch_ohlcv나 check_entry가 호출되지 않아야 함
    mock_bot.fetch_ohlcv.assert_not_called()
    mock_bot.check_entry.assert_not_called()

@pytest.mark.asyncio
async def test_config_structure_consistency():
    # 시나리오: config.example.yaml에 필수 키들이 모두 포함되어 있는지 확인
    from src.config import load_config
    config = load_config()
    
    required_keys = [
        "VERSION", "BINANCE_API_KEY", "TELEGRAM_TOKEN", 
        "SYMBOLS_LIST", "SYMBOL_SETTINGS", "DRY_RUN"
    ]
    for key in required_keys:
        assert key in config, f"Missing required config key: {key}"

if __name__ == "__main__":
    pytest.main([__file__])
