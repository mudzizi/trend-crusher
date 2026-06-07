import pytest
import pandas as pd
import numpy as np
from src.strategy import TrendCrusherV2

@pytest.fixture
def base_config():
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
        "ADX_FILTER_LEVEL": 20,
        "USE_ADAPTIVE_TRAIL": True,
        "ADAPTIVE_TRAIL_STEPS": [
            {"pnl_pct": 10, "atr_mult": 3.5},
            {"pnl_pct": 20, "atr_mult": 2.5}
        ]
    }

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

def test_calculate_position_size(base_config):
    strategy = TrendCrusherV2(config=base_config)
    price = 50000.0
    stop_loss = 49000.0
    qty = strategy.calculate_position_size(price, stop_loss, risk_pct=0.02)
    assert pytest.approx(qty) == 0.2

def test_open_position_state(base_config):
    strategy = TrendCrusherV2(config=base_config)
    direction = 1 
    price = 50000.0
    atr = 500.0
    sl_price = price - (atr * base_config["INITIAL_SL_ATR"])
    timestamp = pd.Timestamp('2024-03-16 12:00:00')
    risk_pct = 0.02
    
    strategy._open_position(direction, price, sl_price, timestamp, risk_pct)
    
    assert strategy.position == 1
    assert strategy.entry_price == 50025.0 # with slippage
    assert strategy.sl_price == 49000.0
    assert strategy.quantity > 0
    assert len(strategy.trades) == 1

def test_close_position_pnl(base_config):
    strategy = TrendCrusherV2(config=base_config)
    strategy.position = 1
    strategy.entry_price = 50000.0
    strategy.quantity = 0.1
    
    strategy._close_position(51000.0, pd.Timestamp.now())
    
    assert strategy.position == 0
    assert strategy.capital == pytest.approx(10097.45)
    assert len(strategy.trades) == 1

def test_adaptive_trailing_stop_logic_real(base_config):
    base_config["USE_ADAPTIVE_TRAIL"] = True
    base_config["ADAPTIVE_TRAIL_STEPS"] = [
        {"pnl_pct": 10.0, "tighten_ratio": 0.5}
    ]
    strategy = TrendCrusherV2(config=base_config)
    row = pd.Series({'atr': 2.0})
    
    # Case 1: PnL < 10% (e.g. 5% profit) -> trailing mult is 4.5.
    # Trail SL = 105.0 - (2.0 * 4.5) = 96.0
    state = {
        'position': 1,
        'entry_price': 100.0,
        'max_price_seen': 105.0,
        'min_price_seen': 100.0,
        'sl_price': 90.0
    }
    strategy.check_exit_signal(row, 105.0, state, base_config)
    assert state['sl_price'] == 96.0
    
    # Case 2: PnL >= 10% (e.g. 12% profit) -> trailing mult is 4.5 * 0.5 = 2.25
    # Trail SL = 112.0 - (2.0 * 2.25) = 107.5
    state2 = {
        'position': 1,
        'entry_price': 100.0,
        'max_price_seen': 112.0,
        'min_price_seen': 100.0,
        'sl_price': 90.0
    }
    strategy.check_exit_signal(row, 112.0, state2, base_config)
    assert state2['sl_price'] == 107.5

def test_retest_maker_entry_and_fee(base_config):
    strategy = TrendCrusherV2(config=base_config)

    # Case A: Market Entry (Taker)
    price = 100.0
    sl_price = 90.0 
    strategy._open_position(1, price, sl_price, pd.Timestamp.now(), 0.02, is_maker=False)
    assert strategy.entry_price == 100.05
    assert strategy.capital == 10000.0 

    # Close at 110.0 (Taker)
    strategy._close_position(110.0, pd.Timestamp.now(), is_maker=False)
    assert strategy.capital == pytest.approx(10195.9199)
    assert strategy.trades[-1]['is_maker'] == False
    
    # Reset
    strategy.capital = 10000.0
    strategy.position = 0
    
    # Case B: Retest Maker Entry
    strategy._open_position(1, 100.0, 90.0, pd.Timestamp.now(), 0.02, is_maker=True)
    assert strategy.capital == 10000.0 
    
    strategy._close_position(110.0, pd.Timestamp.now(), is_maker=True)
    assert strategy.capital == pytest.approx(10199.16)
    assert strategy.trades[-1]['is_maker'] == True

def test_adx_filter_logic_real(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # Base conditions that would trigger a Long entry:
    # last_price > ema_h
    # volume > avg_vol * VOL_MULTIPLIER
    # But ADX is low
    base_config["VOL_MULTIPLIER"] = 1.5
    base_config["ADX_FILTER_LEVEL"] = 20.0
    base_config["CHAOS_THRESHOLD"] = 0.0
    
    row_low_adx = pd.Series({
        'ema_h': 100.0,
        'upper': 105.0,
        'lower': 95.0,
        'atr': 2.0,
        'adx': 15.0,
        'adx_4h': 25.0,
        'volume': 1000.0,
        'avg_vol': 500.0,
        'chop': 50.0,
        'ema_slope': 1.0,
        'chaos': 30.0,
        'squeeze': 0.0
    })
    
    sig_low, _, _ = strategy.check_entry_signal(row_low_adx, 106.0, config=base_config)
    assert sig_low is None
    
    row_high_adx = pd.Series({
        'ema_h': 100.0,
        'upper': 105.0,
        'lower': 95.0,
        'atr': 2.0,
        'adx': 25.0,
        'adx_4h': 25.0,
        'volume': 1000.0,
        'avg_vol': 500.0,
        'chop': 50.0,
        'ema_slope': 1.0,
        'chaos': 30.0,
        'squeeze': 0.0
    })
    sig_high, _, _ = strategy.check_entry_signal(row_high_adx, 106.0, config=base_config)
    assert sig_high == 'MARKET'

def test_v7_chaos_filter(v7_config):
    """Verify that Chaos Index effectively blocks entries below threshold."""
    strategy = TrendCrusherV2(config=v7_config)
    row = pd.Series({
        'volume': 500, 'avg_vol': 100, 'adx': 30, 'adx_4h': 25,
        'ema_h': 1000, 'upper': 1100, 'lower': 900, 'atr': 10,
        'ema_slope': 1.0, 'chaos': 10.0, 'squeeze': 0.0
    })
    
    sig, _, _ = strategy.check_entry_signal(row, 1101, use_sniper=False)
    assert sig is None

def test_v7_slope_filter(v7_config):
    """Verify that EMA Slope blocks counter-trend entries."""
    strategy = TrendCrusherV2(config=v7_config)
    row = pd.Series({
        'volume': 500, 'avg_vol': 100, 'adx': 30, 'adx_4h': 25,
        'ema_h': 1000, 'upper': 1100, 'lower': 900, 'atr': 10,
        'ema_slope': -0.1, 'chaos': 30.0, 'squeeze': 0.0
    })
    
    sig, _, _ = strategy.check_entry_signal(row, 1101, use_sniper=False)
    assert sig is None

def test_v7_asymmetric_short_entry(v7_config):
    """Verify that Shorts have lower entry barriers in V7.0."""
    strategy = TrendCrusherV2(config=v7_config)
    v7_config['VOL_MULTIPLIER'] = 3.0
    v7_config['ADX_FILTER_LEVEL'] = 30.0
    
    row = pd.Series({
        'volume': 200, 'avg_vol': 100, 'adx': 22, 'adx_4h': 12,
        'ema_h': 1000, 'upper': 1100, 'lower': 900, 'atr': 10,
        'ema_slope': -1.0, 'chaos': 30.0, 'squeeze': 0.0
    })
    
    sig, _, _ = strategy.check_entry_signal(row, 899, use_sniper=False, config=v7_config)
    assert sig == 'MARKET'

def test_v7_break_even_guard(v7_config):
    """Verify that SL moves to break-even after 3% profit."""
    strategy = TrendCrusherV2(config=v7_config)
    strategy.capital = 10000
    strategy._open_position(1, 100.0, 95.0, pd.Timestamp.now(), 0.02)
    
    row = pd.Series({'atr': 2.0})
    is_exit = strategy.check_exit_signal(row, 104.0, {
        'position': 1, 'entry_price': strategy.entry_price, 
        'max_price_seen': 104.0, 'min_price_seen': 100.0, 'sl_price': 95.0
    }, v7_config)
    
    assert is_exit is False
    
    is_exit_be = strategy.check_exit_signal(row, 100.05, {
        'position': 1, 'entry_price': strategy.entry_price, 
        'max_price_seen': 104.0, 'min_price_seen': 100.0, 'sl_price': 100.1
    }, v7_config)
    assert is_exit_be is True

def test_v7_fee_settlement_pnl(v7_config):
    """Verify realistic fee settlement at the end of trade."""
    strategy = TrendCrusherV2(config=v7_config)
    strategy.capital = 10000
    
    strategy._open_position(1, 100.0, 90.0, pd.Timestamp.now(), 0.02, is_maker=False)
    strategy._close_position(110.0, pd.Timestamp.now(), is_maker=False)
    
    assert strategy.capital == pytest.approx(10195.9199)
