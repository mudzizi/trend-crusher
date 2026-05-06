import pandas as pd
import numpy as np
from src.indicators import calculate_ema
from src.strategy import TrendCrusherV2

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
    print(f"\nEMA 1000 (span 800): {ema_1000:.4f}")
    print(f"EMA 100 (span 100): {ema_100:.4f}")
    print(f"Difference: {diff_pct:.2f}%")
    
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
    
    # The EMA should move smoothly from T-1 to T
    print(f"EMA at T-1: {ema_t1:.4f}")
    print(f"EMA at T: {ema_t2:.4f}")
    
    # The change should be small and continuous
    change_pct = abs(ema_t2 - ema_t1) / ema_t1 * 100
    assert change_pct < 1.0 # Should be a smooth transition
