import pytest
import asyncio
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch
from scripts.live_bot_async import SymbolBotAsync

@pytest.fixture
def mock_dependencies():
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    # Setup mock PM to return valid quantities
    mock_pm.calculate_order_qty = AsyncMock(return_value=1.0)
    mock_pm.get_total_equity = AsyncMock(return_value=1000.0)
    
    return mock_exchange, mock_pm, mock_notifier, mock_db

def generate_historical_data(symbol, end_ts, count=100):
    """Generate 100 hours of upward trending data."""
    data = []
    base_price = 50000.0
    for i in range(count):
        ts = end_ts - pd.Timedelta(hours=count-i)
        price = base_price + (i * 10) 
        data.append([
            ts, price, price + 50, price - 50, price + 10, 1000.0
        ])
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

@pytest.mark.asyncio
async def test_e2e_trading_cycle_simulation(mock_dependencies):
    mock_exchange, mock_pm, mock_notifier, mock_db = mock_dependencies
    symbol = "BTC/USDT"
    
    bot = SymbolBotAsync(symbol, mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings.update({"DRY_RUN": True})
    
    # Mock Indicators to avoid calculation issues
    bot.df_indicators = pd.DataFrame([{'atr': 100, 'ema_h': 50000, 'upper': 51000, 'lower': 49000, 'volume': 1000, 'avg_vol': 100, 'adx': 30}])
    
    # Scenario: Price is 52000 (Breakout)
    bot.last_price = 52000.0
    
    # Force the engine to return a MARKET signal
    with patch.object(bot.engine, 'check_entry_signal', return_value=('MARKET', 52000.0, 51000.0)):
        await bot.check_entry()
    
    assert bot.position == 1
    assert bot.entry_price == 52000.0
    mock_db.log_trade_open.assert_called()
    
    # 3. Simulate Price Growth
    bot.last_price = 55000.0
    await bot.check_exit() # Should NOT exit yet
    assert bot.max_price_seen == 55000.0
    
    # 4. Simulate Exit Signal
    with patch.object(bot.engine, 'check_exit_signal', return_value=True):
        await bot.check_exit()
    
    assert bot.position == 0
    mock_db.log_trade_close.assert_called()

@pytest.mark.asyncio
async def test_e2e_concurrency_isolation(mock_dependencies):
    mock_exchange, mock_pm, mock_notifier, mock_db = mock_dependencies
    
    bot_btc = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot_eth = SymbolBotAsync("ETH/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    
    for b in [bot_btc, bot_eth]:
        b.settings.update({"DRY_RUN": True})
        b.df_indicators = pd.DataFrame([{'atr': 100, 'ema_h': 50000, 'upper': 51000, 'lower': 49000, 'volume': 1000, 'avg_vol': 100, 'adx': 30}])

    bot_btc.last_price = 60000.0
    with patch.object(bot_btc.engine, 'check_entry_signal', return_value=('MARKET', 60000.0, 59000.0)):
        await bot_btc.check_entry()
    
    assert bot_btc.position != 0
    assert bot_eth.position == 0 
