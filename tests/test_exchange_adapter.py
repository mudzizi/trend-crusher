import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import ccxt.async_support as ccxt
from src.bot.exchange_adapter import ExchangeAdapter

@pytest.mark.asyncio
async def test_exchange_adapter_fetch_ohlcv():
    mock_exchange = MagicMock()
    # Mock return value of fetch_ohlcv
    ohlcv_data = [
        [1717718400000, 68000.0, 68500.0, 67800.0, 68300.0, 150.0],
        [1717722000000, 68300.0, 69000.0, 68200.0, 68900.0, 200.0]
    ]
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=ohlcv_data)
    
    adapter = ExchangeAdapter(mock_exchange, "BTC/USDT")
    df = await adapter.fetch_ohlcv("1h", limit=2)
    
    assert len(df) == 2
    assert df.iloc[0]['close'] == 68300.0
    assert df.iloc[1]['close'] == 68900.0
    mock_exchange.fetch_ohlcv.assert_called_once_with("BTC/USDT", "1h", limit=2)

@pytest.mark.asyncio
async def test_exchange_adapter_retry_success_after_failure():
    mock_exchange = MagicMock()
    
    # Simulate a network failure on first call, success on second
    call_count = 0
    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ccxt.NetworkError("Temporary disconnect")
        return {"id": "ORDER_999", "status": "closed"}
        
    mock_exchange.fetch_order = AsyncMock(side_effect=side_effect)
    
    adapter = ExchangeAdapter(mock_exchange, "BTC/USDT")
    # Set minor delay to speed up tests
    order = await adapter.retry_api_call(mock_exchange.fetch_order, "ORDER_999", delay=0.1)
    
    assert order["id"] == "ORDER_999"
    assert call_count == 2

@pytest.mark.asyncio
async def test_exchange_adapter_retry_max_reached():
    mock_exchange = MagicMock()
    mock_exchange.fetch_order = AsyncMock(side_effect=ccxt.NetworkError("Persistent failure"))
    
    adapter = ExchangeAdapter(mock_exchange, "BTC/USDT")
    
    with pytest.raises(ccxt.NetworkError):
        await adapter.retry_api_call(mock_exchange.fetch_order, "ORDER_999", max_retries=3, delay=0.1)
        
    assert mock_exchange.fetch_order.call_count == 3
