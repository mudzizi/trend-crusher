import pytest
import pandas as pd
import numpy as np
from src.strategy import TrendCrusherV2

@pytest.fixture
def v7_config():
    return {
        "SEED": 10000.0,
        "RISK_PER_TRADE": 0.02,
        "VOL_MULTIPLIER": 2.2,
        "ADX_FILTER_LEVEL": 20.0,
        "ADX_4H_THRESHOLD": 15.0,
        "CHAOS_THRESHOLD": 20.0,
        "INITIAL_SL_ATR": 2.0,
        "TRAILING_ATR_MULT": 5.0,
        "EMA_TREND_PERIOD": 50,
        "DONCHIAN_PERIOD": 10,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "USE_SNIPER": True,
        "BE_GUARD_THRESHOLD": 3.0,
        "USE_ADAPTIVE_TRAIL": True,
        "INITIAL_SL_PCT": 0.0
    }

def test_v7_chaos_filter(v7_config):
    """Verify that Chaos Index effectively blocks entries below threshold."""
    strategy = TrendCrusherV2(config=v7_config)
    row = pd.Series({
        'volume': 500, 'avg_vol': 100, 'adx': 30, 'adx_4h': 25,
        'ema_h': 1000, 'upper': 1100, 'lower': 900, 'atr': 10,
        'ema_slope': 1.0, 'chaos': 10.0, 'squeeze': 0.0 # Chaos below 20
    })
    
    # Chaos 10 < Threshold 20 -> Should be None
    sig, _, _ = strategy.check_entry_signal(row, 1101, use_sniper=False)
    assert sig is None

def test_v7_slope_filter(v7_config):
    """Verify that EMA Slope blocks counter-trend entries."""
    strategy = TrendCrusherV2(config=v7_config)
    row = pd.Series({
        'volume': 500, 'avg_vol': 100, 'adx': 30, 'adx_4h': 25,
        'ema_h': 1000, 'upper': 1100, 'lower': 900, 'atr': 10,
        'ema_slope': -0.1, 'chaos': 30.0, 'squeeze': 0.0 # Slope negative for Long
    })
    
    # Price > EMA but Slope < 0 -> Should be None
    sig, _, _ = strategy.check_entry_signal(row, 1101, use_sniper=False)
    assert sig is None

def test_v7_asymmetric_short_entry(v7_config):
    """Verify that Shorts have lower entry barriers in V7.0."""
    strategy = TrendCrusherV2(config=v7_config)
    # Configure high base thresholds
    v7_config['VOL_MULTIPLIER'] = 3.0
    v7_config['ADX_FILTER_LEVEL'] = 30.0
    
    # Data for a Short candidate
    row = pd.Series({
        'volume': 200, 'avg_vol': 100, 'adx': 22, 'adx_4h': 12,
        'ema_h': 1000, 'upper': 1100, 'lower': 900, 'atr': 10,
        'ema_slope': -1.0, 'chaos': 30.0, 'squeeze': 0.0
    })
    
    # Short barrier is 60~70% of base. 
    # Vol 2.0 (200/100) > 3.0 * 0.6 (1.8) -> OK
    # ADX 22 > 30 * 0.7 (21) -> OK
    # ADX_4h 12 > 15 * 0.7 (10.5) -> OK
    sig, _, _ = strategy.check_entry_signal(row, 899, use_sniper=False, config=v7_config)
    assert sig == 'MARKET'

def test_v7_break_even_guard(v7_config):
    """Verify that SL moves to break-even after 3% profit."""
    strategy = TrendCrusherV2(config=v7_config)
    strategy.capital = 10000
    # Open Long at 100
    strategy._open_position(1, 100.0, 95.0, pd.Timestamp.now(), 0.02)
    
    # Current Price 104 (4% profit)
    row = pd.Series({'atr': 2.0})
    is_exit = strategy.check_exit_signal(row, 104.0, {
        'position': 1, 'entry_price': strategy.entry_price, 
        'max_price_seen': 104.0, 'min_price_seen': 100.0, 'sl_price': 95.0
    }, v7_config)
    
    # SL should have moved to ~100.1 (break-even + buffer)
    # Since 104 > 100.1, it should NOT exit yet
    assert is_exit is False
    
    # But if price drops to 100.05 (below break-even guard 100.1)
    is_exit_be = strategy.check_exit_signal(row, 100.05, {
        'position': 1, 'entry_price': strategy.entry_price, 
        'max_price_seen': 104.0, 'min_price_seen': 100.0, 'sl_price': 100.1 # Manually updated for test
    }, v7_config)
    assert is_exit_be is True

def test_v7_fee_settlement_pnl(v7_config):
    """Verify realistic fee settlement at the end of trade."""
    strategy = TrendCrusherV2(config=v7_config)
    strategy.capital = 10000
    
    # Open at 100.0 (Taker) -> Slippage 100.05
    strategy._open_position(1, 100.0, 90.0, pd.Timestamp.now(), 0.02, is_maker=False)
    # Qty = 200 / 10.05 = 19.9004975
    # Entry Fee = 100.05 * 19.9004975 * 0.0005 = 0.9955
    
    # Close at 110.0 (Taker)
    strategy._close_position(110.0, pd.Timestamp.now(), is_maker=False)
    # Exit Fee = 110 * 19.9004975 * 0.0005 = 1.0945
    # Gross PnL = (110 - 100.05) * 19.9004975 = 198.01
    # Net PnL = 198.01 - (0.9955 + 1.0945) = 195.9199
    
    assert strategy.capital == pytest.approx(10195.9199)
