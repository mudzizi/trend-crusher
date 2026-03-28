import unittest
from unittest.mock import MagicMock, patch
from scripts.dashboard import app
import pandas as pd

class TestDashboard(unittest.TestCase):
    def setUp(self):
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
        
        # New Monitoring Table
        mock_db.get_all_live_status.return_value = pd.DataFrame([{
            'symbol': 'BTC/USDT', 'vol_ratio': 0.5, 'adx_ratio': 0.8, 'prox_ratio': 0.9,
            'trend_ok': 1, 'signal_score': 85.0, 'last_price': 51000.0,
            'upper_band': 52000.0, 'lower_column': 48000.0, 'adx_value': 22.5
        }])

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
    
        response = self.app.get('/')
        # Even with API error, the page should load (graceful degradation)
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
