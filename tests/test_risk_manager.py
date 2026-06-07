import pytest
from unittest.mock import AsyncMock, MagicMock
from src.bot.risk_manager import RiskManager

@pytest.mark.asyncio
async def test_risk_manager_within_limits():
    risk_mgr = RiskManager(dry_run=False)
    
    mock_adapter = MagicMock()
    # Mock current position notional value: $400
    mock_adapter.fetch_positions = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "notional": "400.0"}
    ])
    # Mock open pending orders: 1 order of value $100
    mock_adapter.get_all_open_orders = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "amount": "0.01", "price": "10000.0"}
    ])
    
    # Check entry order of value $200 (Total: 400 + 100 + 200 = 700)
    # limit = $1000
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
    # Mock current position: $600
    mock_adapter.fetch_positions = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "notional": "600.0"}
    ])
    # Mock open orders: $300
    mock_adapter.get_all_open_orders = AsyncMock(return_value=[
        {"symbol": "BTC/USDT", "amount": "0.03", "price": "10000.0"}
    ])
    
    # Check entry order of value $200 (Total: 600 + 300 + 200 = 1100)
    # limit = $1000 -> Should exceed limit
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
    # In dry_run, risk checks should always bypass and return True
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
