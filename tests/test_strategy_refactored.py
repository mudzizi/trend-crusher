import pytest
import pandas as pd
import numpy as np
from src.strategy_numba import numba_check_entry, numba_check_exit
from src.backtest_engine import BacktestEngine
from src.strategy import TrendCrusherV2, get_all_base_bars

def test_numba_check_entry_basic():
    # Simple check that numba_check_entry can be called and returns expected format
    sig_idx, target_p, sl_p = numba_check_entry(
        last_price=105.0, ema_h=100.0, upper=104.0, lower=96.0, atr=2.0, adx=25.0, avg_vol=100.0, volume=300.0,
        vol_mult=1.5, adx_threshold=20.0, initial_sl_atr=2.0,
        use_sniper=False, retest_maker=False, prox_threshold=0.005, is_ambushing=False,
        fixed_sl_pct=0.0, adx_4h=25.0, adx_4h_threshold=20.0,
        chop=50.0, ema_slope=1.0, chaos=30.0, chaos_threshold=20.0, squeeze=0.0
    )
    assert sig_idx == 1 # MARKET
    assert target_p == 105.0
    assert sl_p == 101.0

def test_numba_check_exit_basic():
    # Simple check that numba_check_exit returns expected boolean and new SL
    triggered, new_sl = numba_check_exit(
        last_price=98.0, position=1, entry_price=100.0, max_price_seen=105.0, min_price_seen=100.0, sl_price=95.0,
        atr=2.0, atr_trail_mult=3.0, use_adaptive=False, adaptive_steps_arr=np.zeros((0, 2))
    )
    assert triggered is True # 98.0 <= 105.0 - 2.0 * 3.0 (99.0)
    assert new_sl == 99.0

def test_backtest_engine_delegation():
    # Verify BacktestEngine runs successfully via TrendCrusherV2 delegation
    config = {
        "SEED": 10000.0,
        "RISK_PER_TRADE": 0.02,
        "INITIAL_SL_ATR": 2.0,
        "FEE_RATE": 0.0004,
        "SLIPPAGE": 0.0005,
        "TRAILING_ATR_MULT": 4.5,
        "DONCHIAN_PERIOD": 20,
        "EMA_TREND_PERIOD": 100,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "ADX_FILTER_LEVEL": 20,
        "ADX_4H_THRESHOLD": 15,
        "VOL_MULTIPLIER": 1.5,
        "USE_ADAPTIVE_TRAIL": True,
        "ADAPTIVE_TRAIL_STEPS": [
            {"pnl_pct": 10, "atr_mult": 3.5},
            {"pnl_pct": 20, "atr_mult": 2.5}
        ]
    }
    strategy = TrendCrusherV2(config=config)
    
    # Create simple 1m data (120 rows)
    timestamps = pd.date_range(start='2024-03-16 00:00:00', periods=120, freq='min')
    df_1m = pd.DataFrame({
        'timestamp': timestamps,
        'open': np.linspace(100, 105, 120),
        'high': np.linspace(101, 106, 120),
        'low': np.linspace(99, 104, 120),
        'close': np.linspace(100, 105, 120),
        'volume': np.random.randint(100, 1000, 120)
    })
    
    trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_1m)
    assert isinstance(trades, list)
    assert isinstance(equity_curve, list)
    assert isinstance(df_ind, pd.DataFrame)
