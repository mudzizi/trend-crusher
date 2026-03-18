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
        "TRAILING_ATR_MULT": 4.0,
        "DONCHIAN_PERIOD": 20,
        "EMA_TREND_PERIOD": 100,
        "SIGNAL_TIMEFRAME": "1h",
    }

def test_calculate_position_size(base_config):
    strategy = TrendCrusherV2(config=base_config)
    price = 50000.0
    # Stop distance is 1000 (2% of price)
    # Risk is 200 (2% of 10000)
    # Quantity = 200 / 1000 = 0.2
    stop_loss = 49000.0
    qty = strategy.calculate_position_size(price, stop_loss, risk_pct=0.02)
    assert pytest.approx(qty) == 0.2

def test_open_position_state(base_config):
    strategy = TrendCrusherV2(config=base_config)
    # Mock parameters
    direction = 1 # LONG
    price = 50000.0
    atr = 500.0
    timestamp = pd.Timestamp('2024-03-16 12:00:00')
    risk_pct = 0.02
    
    strategy._open_position(direction, price, atr, timestamp, risk_pct)
    
    assert strategy.position == 1
    # Entry price with slippage: 50000 * 1.0005 = 50025
    assert strategy.entry_price == 50025.0
    # SL price: 50000 - (500 * 2) = 49000
    assert strategy.sl_price == 49000.0
    # Quantity calculation for 49000 SL and 50025 entry (risk is 200)
    # Qty = 200 / (50025 - 49000) = 200 / 1025 approx 0.1951
    assert strategy.quantity > 0
    assert len(strategy.trades) == 1

def test_close_position_pnl(base_config):
    strategy = TrendCrusherV2(config=base_config)
    # Manually set open state
    strategy.position = 1
    strategy.entry_price = 50000.0
    strategy.quantity = 0.1
    initial_cap = strategy.capital # 10000
    
    # Close at 51000 (1000 profit per unit)
    # Raw PnL = 1000 * 0.1 = 100
    # Fee = 51000 * 0.1 * 0.0004 = 2.04
    # Net Capital = 10000 + 100 - 2.04 = 10097.96
    strategy._close_position(51000.0, pd.Timestamp.now())
    
    assert strategy.position == 0
    assert strategy.capital == pytest.approx(10097.96)
    assert len(strategy.trades) == 1


def test_close_position_loss_cap(base_config):
    capped_config = base_config | {"MAX_TRADE_LOSS_PCT_CAP": 2.0}
    strategy = TrendCrusherV2(config=capped_config)
    strategy.position = 1
    strategy.entry_price = 100.0
    strategy.quantity = 20.0
    strategy.capital = 10000.0

    strategy._close_position(80.0, pd.Timestamp.now())

    assert strategy.position == 0
    assert strategy.capital == pytest.approx(9800.0, rel=1e-6)
    assert strategy.trades[0]["cap_applied"] is True


def test_position_size_respects_leverage_and_loss_cap(base_config):
    capped_config = base_config | {"MAX_LEVERAGE": 1.0, "MAX_TRADE_LOSS_PCT_CAP": 1.0}
    strategy = TrendCrusherV2(config=capped_config)
    qty = strategy.calculate_position_size(price=100.0, stop_loss_price=99.0, risk_pct=0.02)

    assert qty == pytest.approx(100.0)
