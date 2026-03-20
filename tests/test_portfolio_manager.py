import unittest
from unittest.mock import MagicMock
from src.portfolio_manager import PortfolioManager

class TestPortfolioManager(unittest.TestCase):
    def setUp(self):
        self.config = {
            "DRY_RUN": True,
            "SEED": 10000.0,
            "RISK_PER_TRADE": 0.02,
            "MAX_CONCURRENT_TRADES": 2,
            "MAX_LEVERAGE": 5,
            "SYMBOL_SETTINGS": {
                "BTC/USDT": {
                    "ALLOCATED_SEED": 10000.0, # Match old test seed for continuity
                    "RISK_PER_TRADE": 0.02
                },
                "ETH/USDT": {
                    "ALLOCATED_SEED": 5000.0,
                    "RISK_PER_TRADE": 0.02
                }
            }
        }
        self.mock_exchange = MagicMock()
        self.pm = PortfolioManager(self.mock_exchange, self.config)
        # Mock DB to return clean slate
        self.pm.db.get_equity_history = MagicMock(return_value=MagicMock(empty=True))
        self.pm.db.get_active_trades = MagicMock(return_value=MagicMock(empty=True, __len__=lambda x: 0))

    def test_calculate_qty_risk_dominant(self):
        # Case: Risk (2%) is the tighter constraint
        # Equity: 10000, Risk: 200
        # Price: 50000, SL: 49000 (Dist: 1000)
        # Risk Qty: 200 / 1000 = 0.2
        # Max Notional: 10000 * 0.5 * 5 = 25000
        # Max Qty: 25000 / 50000 = 0.5
        # Expected: 0.2
        qty = self.pm.calculate_order_qty("BTC/USDT", 50000, 49000)
        self.assertEqual(qty, 0.2)

    def test_calculate_qty_margin_dominant(self):
        # Case: Margin (Seed) is the tighter constraint
        # Symbol Equity: 10000, Risk: 200
        # Price: 50000, SL: 49950 (Dist: 50)
        # Risk Qty: 200 / 50 = 4.0
        # Max Notional: 10000 * 5 (Max Leverage) = 50000
        # Max Qty: 50000 / 50000 = 1.0
        # Expected: 1.0
        qty = self.pm.calculate_order_qty("BTC/USDT", 50000, 49950)
        self.assertEqual(qty, 1.0)

    def test_max_concurrent_trades(self):
        # Mock 2 active trades
        mock_active = MagicMock()
        mock_active.__len__.return_value = 2
        self.pm.db.get_active_trades = MagicMock(return_value=mock_active)
        
        qty = self.pm.calculate_order_qty("ETH/USDT", 2000, 1900)
        self.assertEqual(qty, 0) # Should be skipped
        
if __name__ == '__main__':
    unittest.main()
