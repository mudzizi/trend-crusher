import pytest
import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol
from src.strategy import TrendCrusherV2

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

def test_ema_stability_with_different_data_lengths():
    """
    Verifies that the EMA value for the latest candle is stable 
    when the input data length is sufficient, but can 'kink' 
    if the length falls below the target span due to adaptive logic.
    """
    # Create 1000 bars of mock data (sin wave + trend)
    np.random.seed(42)
    closes = 100 + np.sin(np.linspace(0, 10, 1000)) * 10 + np.linspace(0, 50, 1000)
    df_long = pd.DataFrame({'close': closes, 'high': closes+1, 'low': closes-1, 'volume': 1000})
    
    config = {"EMA_TREND_PERIOD": 200} # Target span = 800
    engine = TrendCrusherV2(config)
    
    # Case A: 1000 bars (Span will be 800)
    df_1000 = engine.calculate_indicators(df_long, df_long, config)
    ema_1000 = df_1000['ema_h'].iloc[-1]
    
    # Case B: 100 bars (Span will be 100 - THIS IS THE BUG SCENARIO)
    df_short = df_long.tail(100).copy()
    df_100 = engine.calculate_indicators(df_short, df_short, config)
    ema_100 = df_100['ema_h'].iloc[-1]
    
    # The values will be significantly different because the span changed from 800 to 100
    diff_pct = abs(ema_1000 - ema_100) / ema_1000 * 100
    
    # In a real scenario, this difference causes the "kink"
    assert diff_pct > 0.1 # Should be a noticeable difference

def test_ema_consistency_with_large_limit():
    """
    Verifies that if we always fetch 1000 bars, the EMA remains stable
    even as a new candle is added.
    """
    np.random.seed(42)
    closes = 100 + np.sin(np.linspace(0, 10, 1001)) * 10 + np.linspace(0, 50, 1001)
    df_full = pd.DataFrame({'close': closes, 'high': closes+1, 'low': closes-1, 'volume': 1000})
    
    config = {"EMA_TREND_PERIOD": 200} # Target span = 800
    engine = TrendCrusherV2(config)
    
    # Snapshot 1: Last 1000 bars (up to T-1)
    df_t1 = df_full.iloc[:-1].tail(1000).copy()
    res_t1 = engine.calculate_indicators(df_t1, df_t1, config)
    ema_t1 = res_t1['ema_h'].iloc[-1]
    
    # Snapshot 2: Last 1000 bars (up to T - including the new candle)
    df_t2 = df_full.tail(1000).copy()
    res_t2 = engine.calculate_indicators(df_t2, df_t2, config)
    ema_t2 = res_t2['ema_h'].iloc[-1]
    
    # The change should be small and continuous
    change_pct = abs(ema_t2 - ema_t1) / ema_t1 * 100
    assert change_pct < 1.0 # Should be a smooth transition
