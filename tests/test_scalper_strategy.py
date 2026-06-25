import pytest
import pandas as pd
import numpy as np
from src.strategy import TrendCrusherScalper

@pytest.fixture
def scalper_config():
    return {
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
        "ADX_FILTER_LEVEL": 20.0,
        "ADX_4H_THRESHOLD": 15.0,
        "CHAOS_THRESHOLD": 0.0, 
        "VOL_MULTIPLIER": 1.5,
        "USE_SNIPER": False,
        "USE_RETEST_MAKER": False,
        "USE_ADAPTIVE_TRAIL": False,
        "INITIAL_SL_PCT": 0.0,
        "BE_GUARD_THRESHOLD": 0.0, 
        "BE_GUARD_THRESHOLD_SCALPER": 1.0,
        "TAKE_PROFIT_ATR_MULT": 1.5,
        "TAKE_PROFIT_PCT": 0.0
    }

def test_scalper_indicators_calculation(scalper_config):
    strategy = TrendCrusherScalper(config=scalper_config)
    df_sig = pd.DataFrame({
        'open': np.linspace(100, 110, 50),
        'high': np.linspace(101, 111, 50),
        'low': np.linspace(99, 109, 50),
        'close': np.linspace(100, 110, 50),
        'volume': np.full(50, 1000.0)
    })
    df_trend = pd.DataFrame({
        'open': np.linspace(100, 110, 15),
        'high': np.linspace(101, 111, 15),
        'low': np.linspace(99, 109, 15),
        'close': np.linspace(100, 110, 15),
        'volume': np.full(15, 4000.0)
    })
    df_res = strategy.calculate_indicators(df_sig, df_trend, scalper_config)
    assert 'atr' in df_res.columns
    assert 'adx_4h' in df_res.columns

def test_scalper_take_profit_atr(scalper_config):
    scalper_config["TAKE_PROFIT_ATR_MULT"] = 2.0
    scalper_config["TAKE_PROFIT_PCT"] = 0.0
    strategy = TrendCrusherScalper(config=scalper_config)
    
    row = pd.Series({'atr': 2.0})
    state = {
        'position': 1,
        'entry_price': 100.0,
        'max_price_seen': 100.0,
        'min_price_seen': 100.0,
        'sl_price': 96.0
    }
    
    is_exit = strategy.check_exit_signal(row, 103.0, state, scalper_config)
    assert is_exit is False
    
    is_exit_tp = strategy.check_exit_signal(row, 104.0, state, scalper_config)
    assert is_exit_tp is True

def test_scalper_take_profit_pct(scalper_config):
    scalper_config["TAKE_PROFIT_ATR_MULT"] = 0.0
    scalper_config["TAKE_PROFIT_PCT"] = 5.0
    strategy = TrendCrusherScalper(config=scalper_config)
    
    row = pd.Series({'atr': 2.0})
    state = {
        'position': -1,
        'entry_price': 100.0,
        'max_price_seen': 100.0,
        'min_price_seen': 100.0,
        'sl_price': 104.0
    }
    
    is_exit = strategy.check_exit_signal(row, 96.0, state, scalper_config)
    assert is_exit is False
    
    is_exit_tp = strategy.check_exit_signal(row, 95.0, state, scalper_config)
    assert is_exit_tp is True

def test_scalper_be_guard_early(scalper_config):
    scalper_config["BE_GUARD_THRESHOLD_SCALPER"] = 1.0
    scalper_config["TAKE_PROFIT_ATR_MULT"] = 0.0
    scalper_config["TAKE_PROFIT_PCT"] = 0.0
    
    strategy = TrendCrusherScalper(config=scalper_config)
    strategy.capital = 10000
    strategy._open_position(1, 100.0, 95.0, pd.Timestamp.now(), 0.02)
    
    state = {
        'position': 1,
        'entry_price': strategy.entry_price,
        'max_price_seen': 101.5,
        'min_price_seen': 100.0,
        'sl_price': 95.0
    }
    
    row = pd.Series({'atr': 2.0})
    is_exit = strategy.check_exit_signal(row, 101.5, state, scalper_config)
    assert is_exit is False
    assert state['sl_price'] == pytest.approx(100.15005)

def test_scalper_find_first_exit(scalper_config):
    scalper_config["TAKE_PROFIT_ATR_MULT"] = 1.5
    strategy = TrendCrusherScalper(config=scalper_config)
    
    closes = np.array([101.0, 102.0, 104.0])
    lookup_indices = np.array([0, 0, 0])
    atrs = np.array([2.0])
    
    exit_idx, max_p, min_p = strategy.find_first_exit(
        closes, lookup_indices, 1, 100.0, 100.0, 100.0, 95.0,
        atrs, 4.5, False, np.zeros((0, 2)), 0.0, scalper_config
    )
    assert exit_idx == 2
