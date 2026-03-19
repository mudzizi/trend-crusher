import pytest
import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol

@pytest.fixture
def mock_ohlcv():
    data = {
        'high': [10, 12, 11, 13, 15, 14, 16, 18, 17, 19, 21, 20],
        'low': [8, 9, 8, 10, 11, 10, 12, 14, 13, 15, 17, 16],
        'close': [9, 11, 10, 12, 14, 13, 15, 17, 16, 18, 20, 19],
        'volume': [100, 120, 110, 130, 150, 140, 160, 180, 170, 190, 210, 200]
    }
    return pd.DataFrame(data)

def test_calculate_donchian(mock_ohlcv):
    period = 5
    upper, lower = calculate_donchian(mock_ohlcv, period=period)
    
    # Donchian은 shift(1)이므로 6번째 행(index 5)의 상단은 이전 5개(0~4) 중 최고가인 15여야 함
    assert upper.iloc[5] == 15
    assert lower.iloc[5] == 8
    assert len(upper) == len(mock_ohlcv)

def test_calculate_ema(mock_ohlcv):
    ema = calculate_ema(mock_ohlcv, period=5)
    assert len(ema) == len(mock_ohlcv)
    assert not ema.isna().all()

def test_calculate_atr(mock_ohlcv):
    atr = calculate_atr(mock_ohlcv, period=5)
    assert len(atr) == len(mock_ohlcv)
    # TR (True Range) 계산이 양수인지 확인
    assert (atr.dropna() > 0).all()

def test_calculate_avg_vol(mock_ohlcv):
    avg_vol = calculate_avg_vol(mock_ohlcv, period=5)
    # shift(1) 확인: 6번째 행은 이전 5개의 평균이어야 함
    expected_avg = np.mean([100, 120, 110, 130, 150])
    assert avg_vol.iloc[5] == expected_avg

def test_calculate_adx(mock_ohlcv):
    from src.indicators import calculate_adx
    adx = calculate_adx(mock_ohlcv, period=5)
    assert len(adx) == len(mock_ohlcv)
    # ADX should be between 0 and 100
    valid_adx = adx.dropna()
    assert (valid_adx >= 0).all()
    assert (valid_adx <= 100).all()
