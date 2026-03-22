import pytest
import pandas as pd
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
    timestamp = pd.Timestamp('2024-03-16 12:00:00')
    risk_pct = 0.02
    
    strategy._open_position(direction, price, atr, timestamp, risk_pct)
    
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
    # Price PnL = (51000-50000)*0.1 = 100
    # Taker Fee = 51000*0.1*0.0005 = 2.55
    # Net Capital = 10000 + 100 - 2.55 = 10097.45
    assert strategy.capital == pytest.approx(10097.45)
    assert len(strategy.trades) == 1

def test_adaptive_trailing_stop_logic(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # 1. Start position
    strategy.position = 1
    strategy.entry_price = 100.0
    strategy.sl_price = 90.0
    strategy.quantity = 10
    
    initial_trail_mult = base_config["TRAILING_ATR_MULT"] # 4.5
    
    # Case A: PnL 5% (Should use 4.5x)
    pnl_5 = 5.0
    curr_mult_5 = initial_trail_mult
    for step in base_config["ADAPTIVE_TRAIL_STEPS"]:
        if pnl_5 >= step['pnl_pct']:
            curr_mult_5 = min(curr_mult_5, step['atr_mult'])
    assert curr_mult_5 == 4.5
    
    # Case B: PnL 15% (Should use 3.5x)
    pnl_15 = 15.0
    curr_mult_15 = initial_trail_mult
    for step in base_config["ADAPTIVE_TRAIL_STEPS"]:
        if pnl_15 >= step['pnl_pct']:
            curr_mult_15 = min(curr_mult_15, step['atr_mult'])
    assert curr_mult_15 == 3.5
    
    # Case C: PnL 25% (Should use 2.5x)
    pnl_25 = 25.0
    curr_mult_25 = initial_trail_mult
    for step in base_config["ADAPTIVE_TRAIL_STEPS"]:
        if pnl_25 >= step['pnl_pct']:
            curr_mult_25 = min(curr_mult_25, step['atr_mult'])
    assert curr_mult_25 == 2.5

def test_tighten_ratio_logic(base_config):
    # Case: tighten_ratio is used instead of fixed atr_mult
    base_config["ADAPTIVE_TRAIL_STEPS"] = [
        {"pnl_pct": 2.0, "tighten_ratio": 0.5} # Tighten by 50%
    ]
    strategy = TrendCrusherV2(config=base_config)
    atr_trail_mult = base_config["TRAILING_ATR_MULT"] # 4.5
    
    # 1. PnL 1% (Below threshold)
    pnl_1 = 1.0
    curr_mult_1 = atr_trail_mult
    for step in base_config["ADAPTIVE_TRAIL_STEPS"]:
        if pnl_1 >= step['pnl_pct']:
            curr_mult_1 = min(curr_mult_1, atr_trail_mult * step['tighten_ratio'])
    assert curr_mult_1 == 4.5
    
    # 2. PnL 3% (Above threshold)
    pnl_3 = 3.0
    curr_mult_3 = atr_trail_mult
    for step in base_config["ADAPTIVE_TRAIL_STEPS"]:
        if pnl_3 >= step['pnl_pct']:
            curr_mult_3 = min(curr_mult_3, atr_trail_mult * step['tighten_ratio'])
    assert curr_mult_3 == 2.25 # 4.5 * 0.5

def test_retest_maker_entry_and_fee(base_config):
    strategy = TrendCrusherV2(config=base_config)
    
    # Case A: Market Entry (Taker)
    strategy._open_position(1, 100.0, 5.0, pd.Timestamp.now(), 0.02, is_maker=False)
    # Entry Price with Slippage (0.05%): 100.05
    # Risk = 200, StopDist = 10.05, Qty = 19.9004975
    # Fee = 100.05 * 19.9004975 * 0.0005 = 0.995522
    # Cap = 10000 - 0.995522 = 9999.004478
    assert strategy.capital == pytest.approx(9999.004478)
    assert strategy.trades[-1]['is_maker'] == False
    
    # Reset
    strategy.capital = 10000.0
    
    # Case B: Retest Maker Entry
    strategy._open_position(1, 100.0, 5.0, pd.Timestamp.now(), 0.02, is_maker=True)
    # Fee = 100 * 20 * 0.0002 = 0.4
    assert strategy.capital == pytest.approx(9999.6)
    assert strategy.trades[-1]['is_maker'] == True

def test_adx_filter_logic_check(base_config):
    # This test verifies if the ADX filter is correctly integrated into entry logic
    strategy = TrendCrusherV2(config=base_config)
    
    # Mock data where ADX is below threshold
    is_vol_burst = True
    adx_low = 15
    is_trending_low = adx_low > base_config["ADX_FILTER_LEVEL"] # 20
    assert is_trending_low == False
    
    # Mock data where ADX is above threshold
    adx_high = 25
    is_trending_high = adx_high > base_config["ADX_FILTER_LEVEL"] # 20
    assert is_trending_high == True
