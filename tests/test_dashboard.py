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
        self.assertIn('+2.00%', content) # (51000-50000)/50000 * 100
        
        # Check if portfolio summary is rendered
        self.assertIn('10,100.00', content) # Current Balance
        self.assertIn('100.0%', content) # Win Rate (1 win, 0 loss)
        
    @patch('scripts.dashboard.exchange')
    def test_dashboard_api_error_handling(self, mock_exchange):
        # Mock API Error
        mock_exchange.fetch_ticker.side_effect = Exception("API Timeout")
        
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dashboard Error', response.data.decode('utf-8'))

if __name__ == '__main__':
    unittest.main()
