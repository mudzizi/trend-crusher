import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from scripts.dashboard import app
import pandas as pd
import pytest
from scripts.live_bot_async import SymbolBotAsync
from src.db_manager import DBManager
from src.config import CONFIG

class TestDashboard(unittest.TestCase):
    def setUp(self):
        from scripts.dashboard import security
        security.password_hash = None
        self.app = app.test_client()
        self.app.testing = True

    @patch('scripts.dashboard.db')
    @patch('scripts.dashboard.exchange')
    @patch('src.visualizer.TradingVisualizer.generate_market_view')
    def test_dashboard_index_with_active_position(self, mock_viz, mock_exchange, mock_db):
        # 1. Mock DB: 1 Active Trade, 1 Closed Trade
        mock_db.get_active_trades.return_value = pd.DataFrame([{
            'symbol': 'BTC/USDT',
            'side': 'LONG',
            'open_price': 50000.0,
            'quantity': 0.1,
            'open_time': '2026-03-20 10:00:00'
        }])
        
        mock_db.get_trade_history.return_value = pd.DataFrame([{
            'id': 1,
            'symbol': 'ETH/USDT',
            'side': 'LONG',
            'open_price': 2000.0,
            'close_price': 2100.0,
            'pnl_pct': 5.0,
            'pnl_usdt': 100.0,
            'close_time': '2026-03-20 09:00:00'
        }])
        
        mock_db.get_equity_history.return_value = pd.DataFrame([{
            'timestamp': '2026-03-20 08:00:00',
            'balance': 10000.0
        }, {
            'timestamp': '2026-03-20 10:00:00',
            'balance': 10100.0
        }])
        
        # Mock Bot State
        mock_db.get_bot_state.return_value = {
            'symbol': 'BTC/USDT',
            'position': 1,
            'entry_price': 50000.0,
            'sl_price': 49000.0,
            'sniper_order_id': None,
            'retest_order_id': None
        }
        
        # New Monitoring Table
        mock_db.get_all_live_status.return_value = pd.DataFrame([{
            'symbol': 'BTC/USDT', 'vol_ratio': 75.0, 'adx_ratio': 80.0, 'prox_ratio': 90.0,
            'trend_ok': 1, 'signal_score': 85.0, 'last_price': 51000.0,
            'upper_band': 52000.0, 'lower_column': 48000.0, 'adx_value': 22.5,
            'adx_4h_value': 18.0, 'chaos_value': 25.0, 'chop_value': 35.0, 'slope_value': 0.005, 'squeeze_value': 0
        }])

        # Hourly History Mock
        mock_db.get_history_1h.return_value = pd.DataFrame({
            'timestamp': ['2026-03-20 08:00:00', '2026-03-20 09:00:00'],
            'close': [50000.0, 51000.0],
            'ema': [49000.0, 49500.0],
            'donchian_upper': [52000.0, 52000.0],
            'donchian_lower': [48000.0, 48000.0],
            'volume': [100.0, 150.0],
            'adx': [20.0, 25.0]
        })

        # 2. Mock Exchange Ticker
        mock_exchange.fetch_ticker.return_value = {'last': 51000.0}

        # 3. Request Dashboard
        response = self.app.get('/')
        
        # 4. Assertions
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        
        # Check if active position is rendered
        self.assertIn('BTC/USDT', content)
        self.assertIn('LONG', content)
        # In new UI, pnl is displayed as 2.0% (without + sign usually, or handled by class)
        self.assertIn('2.0%', content) 
        
        # Check if portfolio summary is rendered
        self.assertIn('10,100.00', content) # Current Balance
        
    @patch('scripts.dashboard.exchange')
    @patch('scripts.dashboard.db')
    def test_dashboard_api_error_handling(self, mock_db, mock_exchange):
        # Mock API Error
        mock_exchange.fetch_ticker.side_effect = Exception("API Timeout")
        mock_db.get_all_live_status.return_value = pd.DataFrame()
        mock_db.get_active_trades.return_value = pd.DataFrame()
        mock_db.get_trade_history.return_value = pd.DataFrame()
        mock_db.get_equity_history.return_value = pd.DataFrame()
        mock_db.get_bot_state.return_value = None
    
        response = self.app.get('/')
        # Even with API error, the page should load (graceful degradation)
        self.assertEqual(response.status_code, 200)

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
            'ema_h': 2450.0, # Price is above EMA (Long bias)
            'chaos': 20.0,
            'squeeze': 0.0,
            'ema_slope': 1.0,
            'chop': 50.0
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
    assert status_df.iloc[0]['prox_ratio'] >= 0
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

@pytest.mark.asyncio
async def test_dynamic_checklist_volume_and_adx_logic(mock_bot, db_manager):
    # Set mock bot attributes
    mock_bot.last_price = 2400.0 # Below EMA 2450.0 -> SHORT candidates
    mock_bot.df_indicators = pd.DataFrame([{
        'timestamp': pd.Timestamp.now(),
        'upper': 2600.0,
        'lower': 2400.0,
        'avg_vol': 100.0,
        'volume': 110.0, # 1.1x avg_vol
        'adx': 20.0,
        'ema_h': 2450.0,
        'chaos': 25.0,
        'squeeze': 1.0,
        'ema_slope': -1.0,
        'chop': 35.0 # < 38.2
    }])
    await mock_bot._record_live_status()
    live_status_df = db_manager.get_all_live_status()
    row = live_status_df.iloc[0]
    
    # Verify signal score calculation works with the dynamic checklist modifications
    assert row['signal_score'] > 0

if __name__ == '__main__':
    unittest.main()
