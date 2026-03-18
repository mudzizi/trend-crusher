import pytest
import pandas as pd
import os
from unittest.mock import MagicMock, patch
from src.data_fetcher import BinanceDataFetcher

@pytest.fixture
def mock_fetcher():
    config = {
        "SYMBOL": "BTC/USDT",
        "DATA_DIR": "test_data",
        "BACKTEST_DAYS": 1,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "CHECK_TIMEFRAME": "1m"
    }
    fetcher = BinanceDataFetcher(config=config)
    # ccxt exchange 모킹
    fetcher.exchange = MagicMock()
    return fetcher

def test_fetch_ohlcv(mock_fetcher):
    # 모킹 데이터 준비
    mock_ohlcv = [
        [1672531200000, 50000, 51000, 49000, 50500, 100],
        [1672534800000, 50500, 52000, 50000, 51500, 150]
    ]
    mock_fetcher.exchange.fetch_ohlcv.return_value = mock_ohlcv
    mock_fetcher.exchange.milliseconds.return_value = 1672534800001
    mock_fetcher.exchange.parse8601.return_value = 1672531100000 # since < milliseconds
    
    df = mock_fetcher.fetch_ohlcv("BTC/USDT", "1h", 1)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert 'timestamp' in df.columns
    assert df.iloc[0]['close'] == 50500

@patch('pandas.DataFrame.to_csv')
def test_save_all(mock_to_csv, mock_fetcher):
    # fetch_ohlcv가 호출될 때마다 빈 DF 반환하도록 모킹
    mock_fetcher.fetch_ohlcv = MagicMock(return_value=pd.DataFrame({'a': [1]}))
    
    mock_fetcher.save_all()
    
    # 설정된 3가지 타임프레임에 대해 각각 저장 시도했는지 확인
    assert mock_fetcher.fetch_ohlcv.call_count == 3
    assert mock_to_csv.call_count == 3
    # 테스트 디렉토리 정리
    if os.path.exists("test_data"):
        import shutil
        shutil.rmtree("test_data")
