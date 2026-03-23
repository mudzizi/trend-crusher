import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from scripts.live_bot_async import SymbolBotAsync
from src.db_manager import DBManager
from src.config import CONFIG

@pytest.fixture
def db_manager(tmp_path):
    # Use a temporary database for testing
    db_file = tmp_path / "test_trading.db"
    return DBManager(str(db_file))

@pytest.fixture
def mock_bot(db_manager):
    config = CONFIG.copy()
    config["DRY_RUN"] = True
    config["SYMBOL"] = "ETH/USDT"
    
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_notifier = MagicMock()
    
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        bot = SymbolBotAsync("ETH/USDT", mock_exchange, mock_pm, mock_notifier, db_manager)
        bot.last_price = 2500.0
        # Setup dummy indicators
        bot.df_indicators = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'upper': 2600.0,
            'lower': 2400.0,
            'avg_vol': 100.0,
            'volume': 150.0, # 1.5x avg_vol
            'adx': 20.0,
            'ema_h': 2450.0 # Price is above EMA (Long bias)
        }])
        return bot

@pytest.mark.asyncio
async def test_record_live_status_updates_db(mock_bot, db_manager):
    # 1. Execute status recording
    await mock_bot._record_live_status()
    
    # 2. Verify DB storage
    status_df = db_manager.get_all_live_status()
    assert not status_df.empty
    assert status_df.iloc[0]['symbol'] == "ETH/USDT"
    
    # 3. Check specific calculation logic
    # Vol Ratio: 150 / (100 * 2.0) = 0.75 (75%)
    assert pytest.approx(status_df.iloc[0]['vol_ratio'], 0.01) == 0.75
    # Price Prox: Current 2500 vs Upper 2600. Sniper Prox limit is 0.5% of 2600 = 13.
    # Dist = 100. Prox Ratio = 1 - (100/13) -> clamped at 0.
    assert status_df.iloc[0]['prox_ratio'] >= 0
    
    # Score should be calculated
    assert status_df.iloc[0]['signal_score'] > 0

@pytest.mark.asyncio
async def test_dashboard_backend_fetches_correct_data(mock_bot, db_manager):
    # Mocking the setup similar to what dashboard.py does
    await mock_bot._record_live_status()
    
    # Simulate dashboard.py fetching
    live_status_df = db_manager.get_all_live_status()
    row = live_status_df.iloc[0]
    
    assert row['symbol'] == "ETH/USDT"
    assert row['trend_ok'] == 1
    assert row['last_price'] == 2500.0
