import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync
import asyncio

@pytest.fixture
def mock_config():
    return {
        "SNIPER_PROXIMITY_PCT": 0.01,
        "VOL_MULTIPLIER": 2.0,
        "ADX_FILTER_LEVEL": 15,
        "EMA_TREND_PERIOD": 100,
        "INITIAL_SL_ATR": 2.0,
        "DRY_RUN": False
    }

@pytest.fixture
def mock_bot(mock_config):
    mock_exchange = MagicMock()
    # Updated: mock create_order to return a specific ID for STOP_MARKET
    mock_exchange.create_order = AsyncMock(return_value={'id': 'stop_market_123'})
    mock_exchange.cancel_order = AsyncMock()
    mock_exchange.fetch_order = AsyncMock(return_value={'id': 'stop_market_123', 'status': 'open'})
    mock_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_exchange.fetch_open_orders = AsyncMock(return_value=[])
    mock_exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 10000.0}})
    mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, q: q)
    
    # CRITICAL: calculate_order_qty MUST BE AsyncMock
    mock_pm = MagicMock()
    mock_pm.calculate_order_qty = AsyncMock(return_value=1.0)
    
    mock_notifier = MagicMock()
    mock_notifier.notify_entry = AsyncMock()
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, MagicMock())
    bot.hot_reload_settings(mock_config)
    bot.settings["MAX_POSITION_VALUE_USDT"] = 1000000.0 # Increase limit for tests
    bot.use_sniper = True
    
    # Setup dummy indicators to bypass basic checks
    bot.df_indicators = pd.DataFrame([{
        'timestamp': pd.Timestamp.now(),
        'atr': 100, 
        'ema_h': 9500, 
        'upper': 10000, 
        'lower': 9000, 
        'volume': 2500, 
        'avg_vol': 1000, 
        'adx': 20
    }])
    return bot

@pytest.mark.asyncio
async def test_sniper_ambush_placed_when_conditions_met(mock_bot):
    # Scenario: Engine signals SNIPER breakout at 10000.0
    with patch.object(mock_bot.engine, 'check_entry_signal', return_value=('SNIPER', 10000.0, 9800.0)):
        await mock_bot.check_entry()
    
    # Assertions: Verify STOP_MARKET was placed instead of LIMIT
    assert mock_bot.active_sniper_order_id == 'stop_market_123'
    
    # Verify create_order was called with correct parameters for STOP_MARKET
    mock_bot.exchange.create_order.assert_called_once()
    args, kwargs = mock_bot.exchange.create_order.call_args
    # create_order signature: symbol, type, side, amount, price, params
    assert args[1] == 'STOP_MARKET'
    assert args[5]['stopPrice'] == 10000.0

@pytest.mark.asyncio
async def test_sniper_ambush_aborted_when_condition_fails(mock_bot):
    # Scenario: Sniper is active but conditions die (engine returns None)
    mock_bot.active_sniper_order_id = 'stop_market_123'
    
    with patch.object(mock_bot.engine, 'check_entry_signal', return_value=(None, None, None)), \
         patch.object(mock_bot, 'fetch_trigger_order', AsyncMock(return_value={'status': 'open'})):
        await mock_bot.check_entry()
    
    assert mock_bot.active_sniper_order_id is None 
    mock_bot.exchange.cancel_order.assert_called_once()

@pytest.mark.asyncio
async def test_sniper_kill_switch_forces_market_order(mock_bot):
    # Scenario: Sniper disabled, engine returns MARKET signal
    mock_bot.use_sniper = False
    mock_bot.execute_entry = AsyncMock()
    
    with patch.object(mock_bot.engine, 'check_entry_signal', return_value=('MARKET', 10050.0, 9850.0)):
        await mock_bot.check_entry()
    
    # Assertions
    mock_bot.execute_entry.assert_called_once()
    assert mock_bot.active_sniper_order_id is None 
