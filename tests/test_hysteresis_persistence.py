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
    row = pd.Series({
        'volume': 180, 'avg_vol': 100, 'adx': 30, 'ema_h': 1000,
        'upper': 1100, 'lower': 900, 'atr': 10
    })
    
    # Normal Check -> None (1.8 < 2.0)
    # Price is 1099 (just below 1100 upper)
    sig, _, _ = strategy.check_entry_signal(row, 1099, use_sniper=True, retest_maker=False, config=base_config, is_ambushing=False)
    assert sig is None
    
    # Ambushing Check -> SNIPER (1.8 > 2.0 * 0.8 = 1.6)
    sig, _, _ = strategy.check_entry_signal(row, 1099, use_sniper=True, retest_maker=False, config=base_config, is_ambushing=True)
    assert sig == 'SNIPER'

def test_hysteresis_adx(base_config):
    strategy = TrendCrusherV2(config=base_config)
    row = pd.Series({
        'volume': 250, 'avg_vol': 100, 'adx': 22, 'ema_h': 1000,
        'upper': 1100, 'lower': 900, 'atr': 10
    })
    
    # Normal Check -> None (22 < 25)
    sig, _, _ = strategy.check_entry_signal(row, 1099, use_sniper=True, retest_maker=False, config=base_config, is_ambushing=False)
    assert sig is None
    
    # Ambushing Check -> SNIPER (22 > 25 * 0.8 = 20)
    sig, _, _ = strategy.check_entry_signal(row, 1099, use_sniper=True, retest_maker=False, config=base_config, is_ambushing=True)
    assert sig == 'SNIPER'

def test_hysteresis_proximity(base_config):
    strategy = TrendCrusherV2(config=base_config)
    row = pd.Series({
        'volume': 250, 'avg_vol': 100, 'adx': 30, 'ema_h': 1000,
        'upper': 1100, 'lower': 900, 'atr': 10
    })
    
    # Dist from upper (1100): Price 1092 -> Dist 8 (0.72%)
    # Limit is 0.5% -> Normal check fails
    sig, _, _ = strategy.check_entry_signal(row, 1092, use_sniper=True, retest_maker=False, config=base_config, is_ambushing=False)
    assert sig is None
    
    # Hysteresis Limit is 1.0% -> Ambushing check passes
    sig, _, _ = strategy.check_entry_signal(row, 1092, use_sniper=True, retest_maker=False, config=base_config, is_ambushing=True)
    assert sig == 'SNIPER'
