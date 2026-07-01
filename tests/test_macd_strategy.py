import pytest
import pandas as pd
import numpy as np
from src.strategy_macd import TrendCrusherMACD

@pytest.fixture
def mock_config():
    return {
        "SEED": 10000.0,
        "SIGNAL_TIMEFRAME": "1h",
    }

def test_calculate_indicators(mock_config):
    strategy = TrendCrusherMACD(config=mock_config)
    
    # Create mock OHLCV dataframe (20 rows to allow EMA initialization to settle)
    closes = [100.0 + i * 2.0 for i in range(20)]  # steadily increasing closes
    df = pd.DataFrame({
        'open': closes,
        'high': [c + 1.0 for c in closes],
        'low': [c - 1.0 for c in closes],
        'close': closes,
        'volume': [1000.0] * 20,
        'timestamp': pd.date_range(start='2026-06-25 00:00:00', periods=20, freq='h')
    })
    
    df_ind = strategy.calculate_indicators(df, None, mock_config)
    
    assert 'macd' in df_ind.columns
    assert 'macd_prev' in df_ind.columns
    assert 'macd_prev2' in df_ind.columns
    assert 'macd_diff' in df_ind.columns
    
    # For index 2, macd_prev should equal macd at index 1, macd_prev2 should equal macd at index 0
    assert df_ind['macd_prev'].iloc[2] == df_ind['macd'].iloc[1]
    assert df_ind['macd_prev2'].iloc[2] == df_ind['macd'].iloc[0]

def test_check_entry_signal(mock_config):
    strategy = TrendCrusherMACD(config=mock_config)
    
    # Case 1: macd_diff < 0 (i.e. MACD increasing) -> MARKET signal, Long
    row_long = pd.Series({'macd_diff': -0.5, 'close': 50000.0})
    sig_t, price, sl = strategy.check_entry_signal(row_long, 50000.0)
    assert sig_t == 'MARKET'
    assert price == 50000.0
    assert sl is None
    
    # Case 2: macd_diff > 0 (i.e. MACD decreasing) -> MARKET signal, Short
    row_short = pd.Series({'macd_diff': 0.8, 'close': 50000.0})
    sig_t, price, sl = strategy.check_entry_signal(row_short, 50000.0)
    assert sig_t == 'MARKET'
    assert price == 50000.0
    assert sl is None

    # Case 3: macd_diff is NaN/0 -> None
    row_none = pd.Series({'macd_diff': 0.0, 'close': 50000.0})
    sig_t, price, sl = strategy.check_entry_signal(row_none, 50000.0)
    assert sig_t is None

def test_position_transitions(mock_config):
    strategy = TrendCrusherMACD(config=mock_config)
    
    # Initialize capital
    strategy.capital = 10000.0
    
    # 1. Open Long position at 1000
    timestamp_1 = pd.Timestamp('2026-06-25 12:00:00')
    strategy._open_position(1, 1000.0, timestamp_1)
    
    assert strategy.position == 1
    # 1000 + 0.05% slippage (0.5) = 1000.5
    assert strategy.entry_price == 1000.5
    # Quantity = 10000 / 1000.5
    expected_qty = 10000.0 / 1000.5
    assert strategy.quantity == expected_qty
    
    # 2. Close Long (which reverses to Short) at 1200
    timestamp_2 = pd.Timestamp('2026-06-25 13:00:00')
    strategy._close_position(1200.0, timestamp_2)
    
    # Exit price = 1200 - 0.05% slippage (0.6) = 1199.4
    exit_p = 1199.4
    # Entry fee = 1000.5 * qty * 0.05% = 10000 * 0.0005 = 5.0
    # Exit fee = 1199.4 * qty * 0.05%
    entry_fee = 5.0
    exit_fee = exit_p * expected_qty * 0.0005
    pnl = (exit_p - 1000.5) * expected_qty
    net_pnl = pnl - (entry_fee + exit_fee)
    
    assert strategy.position == 0
    assert strategy.capital == pytest.approx(10000.0 + net_pnl)
    assert len(strategy.trades) == 2  # one OPEN, one CLOSE

def test_stop_loss_trigger(mock_config):
    mock_config["STOP_LOSS_PCT"] = 0.02  # 2% Stop Loss
    strategy = TrendCrusherMACD(config=mock_config)
    
    # Open Long at 1000. Entry price = 1000.5 (with slippage)
    # Stop loss price = 1000.5 * 0.98 = 980.49
    strategy.capital = 10000.0
    strategy._open_position(1, 1000.0, pd.Timestamp('2026-06-25 12:00:00'))
    
    assert strategy.sl_price == pytest.approx(980.49)
    assert strategy.position == 1
    
    # Simulate a candle low price triggering the stop loss
    low_price = 975.0
    timestamp = pd.Timestamp('2026-06-25 13:00:00')
    
    if strategy.position == 1 and strategy.sl_price > 0.0:
        if low_price <= strategy.sl_price:
            strategy._close_position(strategy.sl_price, timestamp, exit_type='SL')
            
    assert strategy.position == 0
    assert len(strategy.trades) == 2
    assert strategy.trades[-1]['type'] == 'SL'
    # Exit price = sl_price (980.49) - slippage (980.49 * 0.0005) = 980.0
    assert strategy.trades[-1]['price'] == pytest.approx(980.49 - (980.49 * 0.0005))

def test_ema_filter(mock_config):
    # Enable EMA Filter
    mock_config["USE_EMA_FILTER"] = True
    mock_config["EMA_FILTER_SPAN"] = 200
    strategy = TrendCrusherMACD(config=mock_config)
    
    # Case 1: Close is above EMA filter -> Long allowed, Short blocked
    row_above = pd.Series({
        'macd_diff': -0.5,           # Long signal
        'close_prev': 105.0,
        'ema_filter_prev': 100.0,
        'adx_prev': 0.0,
        'chop_prev': 0.0,
        'squeeze_prev': 0.0
    })
    sig_t, _, _ = strategy.check_entry_signal(row_above, 105.0)
    assert sig_t == 'MARKET'  # Long allowed
    
    row_above_short = pd.Series({
        'macd_diff': 0.5,            # Short signal
        'close_prev': 105.0,
        'ema_filter_prev': 100.0,
        'adx_prev': 0.0,
        'chop_prev': 0.0,
        'squeeze_prev': 0.0
    })
    sig_t, _, _ = strategy.check_entry_signal(row_above_short, 105.0)
    assert sig_t is None      # Short blocked
    
    # Case 2: Close is below EMA filter -> Short allowed, Long blocked
    row_below = pd.Series({
        'macd_diff': -0.5,           # Long signal
        'close_prev': 95.0,
        'ema_filter_prev': 100.0,
        'adx_prev': 0.0,
        'chop_prev': 0.0,
        'squeeze_prev': 0.0
    })
    sig_t, _, _ = strategy.check_entry_signal(row_below, 95.0)
    assert sig_t is None      # Long blocked
    
    row_below_short = pd.Series({
        'macd_diff': 0.5,            # Short signal
        'close_prev': 95.0,
        'ema_filter_prev': 100.0,
        'adx_prev': 0.0,
        'chop_prev': 0.0,
        'squeeze_prev': 0.0
    })
    sig_t, _, _ = strategy.check_entry_signal(row_below_short, 95.0)
    assert sig_t == 'MARKET'  # Short allowed

