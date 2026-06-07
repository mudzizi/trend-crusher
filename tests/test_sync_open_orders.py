import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from scripts.live_bot_async import SymbolBotAsync
from src.config import CONFIG

@pytest.fixture
def mock_bot():
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
async def test_sync_all_orders_robust_symbol_matching(mock_bot):
    mock_bot.exchange.fetch_positions.return_value = [
        {'symbol': 'SUI/USDT:USDT', 'contracts': '100', 'entryPrice': '1.5', 'side': 'long'}
    ]
    mock_bot.exchange.fetch_open_orders.return_value = []
    
    await mock_bot.sync_all_orders()
    
    assert mock_bot.position == 1
    assert mock_bot.entry_price == 1.5
    assert mock_bot.quantity == 100.0

@pytest.mark.asyncio
async def test_sync_all_orders_synchronizes_sniper_and_retest_when_idle(mock_bot):
    mock_bot.exchange.fetch_positions.return_value = [
        {'symbol': 'SUI/USDT:USDT', 'contracts': '0', 'entryPrice': '0', 'side': 'long'}
    ]
    mock_bot.exchange.fetch_open_orders.return_value = [
        {'id': 'sniper_123', 'type': 'STOP_MARKET', 'amount': '50', 'stopPrice': '1.6'},
        {'id': 'retest_456', 'type': 'LIMIT', 'amount': '30', 'price': '1.4'}
    ]
    
    await mock_bot.sync_all_orders()
    
    assert mock_bot.position == 0
    assert mock_bot.active_sniper_order_id == 'sniper_123'
    assert mock_bot.active_retest_order_id == 'retest_456'
    assert mock_bot.quantity == 30.0
