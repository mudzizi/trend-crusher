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
    config["SYMBOL"] = "BTC/USDT"
    
    # Mock dependencies
    mock_db = MagicMock()
    mock_pm = AsyncMock()
    mock_exchange = AsyncMock()
    mock_notifier = MagicMock()
    
    # Initialize Bot (symbol, exchange, pm, notifier, db)
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        mock_exchange.fetch_positions = AsyncMock(return_value=[])
        mock_exchange.fetch_open_orders = AsyncMock(return_value=[])
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.settings = config
        bot.settings["MAX_POSITION_VALUE_USDT"] = 1000000.0 # Increase limit for tests
        bot.last_price = 50000.0
        bot.ohlcv_1h = pd.DataFrame([{'timestamp': pd.Timestamp.now(), 'atr': 100.0}])
        bot.entry_price = 0
        bot.quantity = 0
        return bot

@pytest.mark.asyncio
async def test_execute_entry_syncs_with_exchange(mock_bot):
    # Mock exchange response for MARKET entry
    mock_bot.exchange.create_market_order.return_value = {
        'id': '123',
        'symbol': 'BTC/USDT',
        'side': 'buy',
        'average': 50100.0,
        'filled': 0.1,
        'status': 'closed'
    }
    mock_bot.exchange.create_order.return_value = {'id': 'sl_123'}
    mock_bot.pm.calculate_order_qty.return_value = 0.1
    # Added mocks for Margin Safety Guard
    mock_bot.exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 10000.0}})
    mock_bot.exchange.amount_to_precision = MagicMock(side_effect=lambda s, q: q)
    mock_bot.exchange.fetch_positions = AsyncMock(return_value=[{'symbol': 'BTC/USDT', 'contracts': 0}])

    # Execute Entry
    await mock_bot.execute_entry(1, 100.0)

    # Verify
    assert mock_bot.entry_price == 50100.0
    assert mock_bot.quantity == 0.1
    assert mock_bot.position == 1
    mock_bot.db.log_trade_open.assert_called()

@pytest.mark.asyncio
async def test_execute_exit_calculates_real_pnl(mock_bot):
    # Setup open position
    mock_bot.position = 1
    mock_bot.entry_price = 50000.0
    mock_bot.quantity = 0.1
    mock_bot.last_price = 55000.0
    
    # Mock exchange response
    mock_bot.exchange.create_order.return_value = {
        'average': 55000.0,
        'filled': 0.1,
        'fee': {'cost': 2.75}
    }
    mock_bot.pm.get_total_equity.return_value = 10500.0

    # Execute Exit
    await mock_bot.execute_exit()

    # Verify PnL calculation and recording
    args = mock_bot.db.log_trade_close.call_args[0]
    assert args[1] == 55000.0 # exit price
    assert pytest.approx(args[3], 0.1) == 497.25 # pnl_usdt

@pytest.mark.asyncio
async def test_force_exit_logic(mock_bot):
    # Mock real position
    mock_bot.exchange.fetch_positions.return_value = [
        {'symbol': 'BTC/USDT', 'contracts': '0.05'}
    ]
    mock_bot.exchange.create_order.return_value = {
        'average': 50000.0, 
        'filled': 0.05,
        'fee': {'cost': 1.25}
    }
    mock_bot.entry_price = 49000.0
    mock_bot.position = 1
    mock_bot.quantity = 0.05
    
    # Execute Force Exit
    await mock_bot.force_exit()

    # Verify closure
    mock_bot.exchange.create_order.assert_any_call("BTC/USDT", "market", "sell", 0.05, None, params={'reduceOnly': True})
    assert mock_bot.position == 0
    mock_bot.db.log_trade_close.assert_called()
