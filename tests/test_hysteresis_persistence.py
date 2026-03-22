import pytest
import pandas as pd
from src.strategy import TrendCrusherV2

@pytest.fixture
def base_config():
    return {
        "SEED": 10000.0,
        "RISK_PER_TRADE": 0.02,
        "INITIAL_SL_ATR": 2.0,
        "VOL_MULTIPLIER": 2.0,
        "ADX_FILTER_LEVEL": 25,
        "SNIPER_PROXIMITY_PCT": 0.005, # 0.5%
        "DONCHIAN_PERIOD": 20,
        "EMA_TREND_PERIOD": 100,
        "SIGNAL_TIMEFRAME": "1h",
        "USE_SNIPER": True
    }

def test_hysteresis_volume_burst(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # Mock row where volume is 1.8x (below 2.0x threshold, but above 1.6x hysteresis)
    row = pd.Series({
        'volume': 180,
        'avg_vol': 100,
        'adx': 30,
        'ema_h': 1000,
        'upper': 1100,
        'lower': 900,
        'atr': 10,
        'prev_volume': 0,
        'prev_avg_vol': 0
    })
    
    # Normal Check (is_ambushing=False) -> Should be None
    sig, _, _ = strategy.check_entry_signal(row, 1102, use_sniper=True, is_ambushing=False)
    assert sig is None
    
    # Ambushing Check (is_ambushing=True) -> Should maintain Sniper signal (1.8 > 2.0 * 0.8 = 1.6)
    sig, _, _ = strategy.check_entry_signal(row, 1102, use_sniper=True, is_ambushing=True)
    assert sig == 'SNIPER'

def test_hysteresis_adx(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # Mock row where ADX is 22 (below 25 threshold, but above 20 hysteresis)
    row = pd.Series({
        'volume': 250,
        'avg_vol': 100,
        'adx': 22,
        'ema_h': 1000,
        'upper': 1100,
        'lower': 900,
        'atr': 10,
        'prev_volume': 0,
        'prev_avg_vol': 0
    })
    
    # Normal Check -> None
    sig, _, _ = strategy.check_entry_signal(row, 1102, use_sniper=True, is_ambushing=False)
    assert sig is None
    
    # Ambushing Check -> SNIPER (22 > 25 * 0.8 = 20)
    sig, _, _ = strategy.check_entry_signal(row, 1102, use_sniper=True, is_ambushing=True)
    assert sig == 'SNIPER'

def test_hysteresis_proximity(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # Upper is 1100. 0.5% proximity is 5.5. Range: 1094.5 - 1105.5
    # Price is 1108 (0.72% away from 1100)
    # Normal prox check: 8/1100 = 0.0072 > 0.005 -> Fails
    # Hysteresis prox check: 0.0072 < 0.005 * 2.0 (0.01) -> Passes
    
    row = pd.Series({
        'volume': 250,
        'avg_vol': 100,
        'adx': 30,
        'ema_h': 1000,
        'upper': 1100,
        'lower': 900,
        'atr': 10,
        'prev_volume': 0,
        'prev_avg_vol': 0
    })
    
    # Normal Check -> None (Too far for ambush, and not yet closed above for market fallback in this specific condition)
    # Actually Sniper Fallback triggers if last_price >= upper. Let's test just below upper.
    # Upper is 1100. Price 1092 (Dist 8 = 0.72%)
    sig, _, _ = strategy.check_entry_signal(row, 1092, use_sniper=True, is_ambushing=False)
    assert sig is None
    
    # Ambushing Check -> SNIPER (0.0072 <= 0.01)
    sig, _, _ = strategy.check_entry_signal(row, 1092, use_sniper=True, is_ambushing=True)
    assert sig == 'SNIPER'

def test_volume_persistence_candle_transition(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # Case: New candle just started. Current volume is low (10), but previous bar was a burst (250/100)
    row = pd.Series({
        'volume': 10,
        'avg_vol': 100,
        'adx': 30,
        'ema_h': 1000,
        'upper': 1100,
        'lower': 900,
        'atr': 10,
        'prev_volume': 250,
        'prev_avg_vol': 100
    })
    
    # Normal Check (is_ambushing=False) -> Should still trigger/maintain because of prev_burst
    sig, _, _ = strategy.check_entry_signal(row, 1102, use_sniper=True, is_ambushing=False)
    assert sig == 'SNIPER'
    
    # Even if current ADX is slightly low but we are ambushing
    row_weak_adx = row.copy()
    row_weak_adx['adx'] = 22 # Below 25
    
    sig, _, _ = strategy.check_entry_signal(row_weak_adx, 1102, use_sniper=True, is_ambushing=True)
    assert sig == 'SNIPER'
