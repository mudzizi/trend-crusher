import pytest
import pandas as pd
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync

@pytest.fixture
def mock_bot():
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    settings = {
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "DRY_RUN": False,
        "TRAILING_ATR_MULT": 3.0,
        "INITIAL_SL_ATR": 2.0
    }
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings = settings
    bot.last_price = 50000.0
    bot.last_sl_sync_price = 0
    
    # Mock OHLCV
    now = pd.Timestamp.now().floor('h')
    data = [[now, 50000, 51000, 49000, 50000, 1000]]
    bot.ohlcv_1h = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    bot.ohlcv_4h = bot.ohlcv_1h.copy()
    
    # Mock Indicators DataFrame
    bot.df_indicators = pd.DataFrame(
        [{'close': 50000, 'atr': 1000, 'ema_h': 45000, 'upper': 52000, 'lower': 48000}],
        index=[now]
    )
    
    return bot

@pytest.mark.asyncio
async def test_sl_fill_with_id_mismatch(mock_bot):
    """Scenario: SL fills with a DIFFERENT order_id. Bot should still exit."""
    mock_bot.position = 1 # LONG
    mock_bot.entry_price = 48000.0
    mock_bot.sl_order_id = "OLD_ID_123"
    mock_bot.quantity = 1.0
    
    # Simulate a fill event with a NEW ID (Opposite side: SELL)
    order_data = {
        'i': 'NEW_ID_456', # Mismatch!
        's': 'BTCUSDT',
        'X': 'FILLED',
        'S': 'SELL', 
        'z': '1.0',
        'ap': '49500',
        'L': '49500' # Add missing 'L' key to avoid KeyError
    }
    
    # Mock sync_all_orders to avoid actual API call
    with patch.object(mock_bot, 'sync_all_orders', new_callable=AsyncMock):
        await mock_bot.on_order_update(order_data)
        
        # Verification: Position should be reset to 0
        assert mock_bot.position == 0
        assert mock_bot.entry_price == 0
        assert mock_bot.sl_order_id is None
        # Trade Close should be logged
        mock_bot.db.log_trade_close.assert_called()

@pytest.mark.asyncio
async def test_no_market_order_on_sl_hit(mock_bot):
    """Scenario: Price hits SL. Bot should NOT send market order, wait for fill."""
    mock_bot.position = 1 # LONG
    mock_bot.sl_price = 49000.0
    mock_bot.last_price = 48500.0 # Price is below SL
    mock_bot.sl_order_id = "SL_123"
    
    # Mock engine to trigger exit signal
    mock_bot.engine.check_exit_signal = MagicMock(return_value=True)
    # Mock execute_exit to verify it is NOT called
    mock_bot.execute_exit = AsyncMock()
    
    await mock_bot.check_exit()
    
    # Verification: execute_exit (market order) should NOT be called
    mock_bot.execute_exit.assert_not_called()
    assert mock_bot.position == 1 # Stays until WS FILL confirms

@pytest.mark.asyncio
async def test_emergency_sync_when_sl_missing(mock_bot):
    """Scenario: Position exists but SL order ID is missing. Trigger sync/exit."""
    mock_bot.position = -1 # SHORT
    mock_bot.sl_order_id = None # CRITICAL MISSING ID
    
    with patch.object(mock_bot, 'sync_all_orders', new_callable=AsyncMock) as mock_sync:
        with patch.object(mock_bot, 'execute_exit', new_callable=AsyncMock) as mock_exit:
            await mock_bot.check_exit()
            
            # Should try to sync first
            mock_sync.assert_called_once()
            # Since sl_order_id is still None, should trigger emergency exit
            mock_exit.assert_called_once()

@pytest.mark.asyncio
async def test_trailing_sl_sync_trigger(mock_bot):
    """Scenario: Trailing SL moves significantly. Should trigger exchange sync."""
    mock_bot.position = 1
    mock_bot.sl_order_id = "SL_123"
    mock_bot.sl_price = 49000.0
    mock_bot.last_sl_sync_price = 48000.0 # Diff > 0.05%
    
    # Mock engine to update SL but NOT trigger exit
    mock_bot.engine.check_exit_signal = MagicMock(return_value=False)
    
    with patch.object(mock_bot, 'sync_sl_to_exchange', new_callable=AsyncMock) as mock_sl_sync:
        await mock_bot.check_exit()
        # Should trigger sync to exchange
        mock_sl_sync.assert_called_once()
