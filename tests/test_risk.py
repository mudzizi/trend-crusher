import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock
from scripts.live_bot_async import SymbolBotAsync
from src.portfolio_manager_async import PortfolioManagerAsync
from src.bot.risk_manager import RiskManager

@pytest.fixture
def mock_bot():
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    bot = SymbolBotAsync("TRUMP/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    
    # Mock settings
    bot.settings = {
        "RISK_PER_TRADE": 0.02,
        "MAX_LEVERAGE": 5.0,
        "DRY_RUN": True,
        "SYMBOL_SETTINGS": {
            "TRUMP/USDT": {
                "ALLOCATED_SEED": 1000.0,
                "RISK_PER_TRADE": 0.02
            }
        }
    }
    
    # Mock exchange market data
    mock_exchange.market = MagicMock(return_value={
        'symbol': 'TRUMP/USDT',
        'precision': {'amount': 1, 'price': 3},
        'limits': {
            'amount': {'min': 0.1, 'max': 100000.0},
            'cost': {'min': 5.0}
        }
    })
    
    # Mock amount_to_precision
    mock_exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{float(a):.1f}")
    
    return bot

@pytest.mark.asyncio
async def test_async_leverage_cap_safety(mock_bot):
    # Scenario: Narrow stop loss leading to high leverage
    # Entry: 10.0, SL: 9.99 (0.1% dist)
    # Risk 2% of 1000 = 20. Qty = 20 / 0.01 = 2000 (Notional 20,000, Leverage 20x)
    # Max Leverage 5x -> Max Notional 5000 -> Max Qty 500
    
    real_pm = PortfolioManagerAsync(mock_bot.exchange, mock_bot.settings)
    real_pm.db = MagicMock()
    real_pm.db.get_active_trades.return_value = []
    real_pm.db.get_equity_history.return_value = pd.DataFrame([{'balance': 1000.0}])
    
    qty = await real_pm.calculate_order_qty("TRUMP/USDT", 10.0, 9.99)
    assert qty == 500.0

@pytest.mark.asyncio
async def test_async_safety_limit_check(mock_bot):
    mock_bot.settings["DRY_RUN"] = False
    mock_bot.risk_manager.dry_run = False
    mock_bot.risk_manager.check_exposure_safety = AsyncMock(return_value=False)
    
    over_limit = await mock_bot._is_over_safety_limit(500.0)
    assert over_limit is True

# --- From test_risk_manager.py ---
@pytest.mark.asyncio
async def test_risk_manager_within_limits():
    risk_mgr = RiskManager(dry_run=False)
    mock_adapter = MagicMock()
    mock_adapter.fetch_positions = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "notional": "400.0"}
    ])
    mock_adapter.get_all_open_orders = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "amount": "0.01", "price": "10000.0"}
    ])
    
    safe = await risk_mgr.check_exposure_safety(
        symbol="BTC/USDT",
        last_price=50000.0,
        new_order_value_usdt=200.0,
        exchange_adapter=mock_adapter,
        max_position_value_usdt=1000.0
    )
    assert safe is True

@pytest.mark.asyncio
async def test_risk_manager_exceeds_limits():
    risk_mgr = RiskManager(dry_run=False)
    mock_adapter = MagicMock()
    mock_adapter.fetch_positions = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "notional": "600.0"}
    ])
    mock_adapter.get_all_open_orders = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "amount": "0.03", "price": "10000.0"}
    ])
    
    safe = await risk_mgr.check_exposure_safety(
        symbol="BTC/USDT",
        last_price=50000.0,
        new_order_value_usdt=200.0,
        exchange_adapter=mock_adapter,
        max_position_value_usdt=1000.0
    )
    assert safe is False

@pytest.mark.asyncio
async def test_risk_manager_dry_run():
    risk_mgr = RiskManager(dry_run=True)
    mock_adapter = MagicMock()
    mock_adapter.fetch_positions = AsyncMock(side_effect=Exception("Should not be called"))
    
    safe = await risk_mgr.check_exposure_safety(
        symbol="BTC/USDT",
        last_price=50000.0,
        new_order_value_usdt=5000.0,
        exchange_adapter=mock_adapter,
        max_position_value_usdt=1000.0
    )
    assert safe is True
