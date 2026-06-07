import pytest
import pandas as pd
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync
from src.config import CONFIG

@pytest.fixture
def mock_bot():
    config = CONFIG.copy()
    config["DRY_RUN"] = False
    config["SYMBOL"] = "BTC/USDT"
    
    mock_db = MagicMock()
    mock_pm = AsyncMock()
    mock_exchange = AsyncMock()
    mock_notifier = MagicMock()
    
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.settings = config
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

# --- From test_sl_robustness.py ---
@pytest.mark.asyncio
async def test_sl_fill_with_id_mismatch(mock_bot):
    """Scenario: SL fills with a DIFFERENT order_id. Bot should still exit."""
    mock_bot.position = 1 # LONG
    mock_bot.entry_price = 48000.0
    mock_bot.sl_order_id = "OLD_ID_123"
    mock_bot.quantity = 1.0
    
    order_data = {
        'i': 'NEW_ID_456', # Mismatch!
        's': 'BTCUSDT',
        'X': 'FILLED',
        'S': 'SELL', 
        'z': '1.0',
        'ap': '49500',
        'L': '49500'
    }
    
    with patch.object(mock_bot, 'sync_all_orders', new_callable=AsyncMock):
        await mock_bot.on_order_update(order_data)
        assert mock_bot.position == 0
        assert mock_bot.entry_price == 0
        assert mock_bot.sl_order_id is None
        mock_bot.db.log_trade_close.assert_called()

@pytest.mark.asyncio
async def test_no_market_order_on_sl_hit(mock_bot):
    """Scenario: Price hits SL. Bot should NOT send market order, wait for fill."""
    mock_bot.position = 1 # LONG
    mock_bot.sl_price = 49000.0
    mock_bot.last_sl_sync_price = 49000.0
    mock_bot.last_price = 48500.0
    mock_bot.sl_order_id = "SL_123"
    
    mock_bot.engine.check_exit_signal = MagicMock(return_value=True)
    mock_bot.execute_exit = AsyncMock()
    
    await mock_bot.check_exit()
    mock_bot.execute_exit.assert_not_called()
    assert mock_bot.position == 1

@pytest.mark.asyncio
async def test_emergency_sync_when_sl_missing(mock_bot):
    """Scenario: Position exists but SL order ID is missing. Trigger sync/exit."""
    mock_bot.position = -1 # SHORT
    mock_bot.entry_price = 50000.0
    mock_bot.sl_order_id = None
    
    with patch.object(mock_bot, 'sync_all_orders', new_callable=AsyncMock) as mock_sync:
        with patch.object(mock_bot, 'execute_exit', new_callable=AsyncMock) as mock_exit:
            await mock_bot.check_exit()
            mock_sync.assert_called_once()
            mock_exit.assert_not_called()
            mock_bot.notifier.send_message.assert_called()

@pytest.mark.asyncio
async def test_trailing_sl_sync_trigger(mock_bot):
    """Scenario: Trailing SL moves significantly. Should trigger exchange sync."""
    mock_bot.position = 1
    mock_bot.sl_order_id = "SL_123"
    mock_bot.sl_price = 49000.0
    mock_bot.last_sl_sync_price = 48000.0
    
    mock_bot.engine.check_exit_signal = MagicMock(return_value=False)
    
    with patch.object(mock_bot, 'sync_sl_to_exchange', new_callable=AsyncMock) as mock_sl_sync:
        await mock_bot.check_exit()
        mock_sl_sync.assert_called_once()

# --- From test_sync_open_orders.py ---
@pytest.fixture
def mock_bot_sui():
    config = CONFIG.copy()
    config["DRY_RUN"] = False
    config["SYMBOL"] = "SUI/USDT"
    
    mock_db = MagicMock()
    mock_pm = AsyncMock()
    mock_exchange = AsyncMock()
    mock_notifier = MagicMock()
    
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        bot = SymbolBotAsync("SUI/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.settings = config
        bot.last_price = 1.5
        bot.ohlcv_1h = pd.DataFrame([{'timestamp': pd.Timestamp.now(), 'atr': 0.1}])
        bot.entry_price = 0
        bot.quantity = 0
        return bot

@pytest.mark.asyncio
async def test_sync_all_orders_robust_symbol_matching(mock_bot_sui):
    mock_bot_sui.exchange.fetch_positions.return_value = [
        {'symbol': 'SUI/USDT:USDT', 'contracts': '100', 'entryPrice': '1.5', 'side': 'long'}
    ]
    mock_bot_sui.exchange.fetch_open_orders.return_value = []
    
    await mock_bot_sui.sync_all_orders()
    
    assert mock_bot_sui.position == 1
    assert mock_bot_sui.entry_price == 1.5
    assert mock_bot_sui.quantity == 100.0

@pytest.mark.asyncio
async def test_sync_all_orders_synchronizes_sniper_and_retest_when_idle(mock_bot_sui):
    mock_bot_sui.exchange.fetch_positions.return_value = [
        {'symbol': 'SUI/USDT:USDT', 'contracts': '0', 'entryPrice': '0', 'side': 'long'}
    ]
    mock_bot_sui.exchange.fetch_open_orders.return_value = [
        {'id': 'sniper_123', 'type': 'STOP_MARKET', 'amount': '50', 'stopPrice': '1.6'},
        {'id': 'retest_456', 'type': 'LIMIT', 'amount': '30', 'price': '1.4'}
    ]
    
    await mock_bot_sui.sync_all_orders()
    
    assert mock_bot_sui.position == 0
    assert mock_bot_sui.active_sniper_order_id == 'sniper_123'
    assert mock_bot_sui.active_retest_order_id == 'retest_456'
    assert mock_bot_sui.quantity == 30.0
