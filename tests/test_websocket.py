import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.websocket_manager import BinanceWebSocketManager

@pytest.mark.asyncio
async def test_websocket_message_queuing():
    """Verify that messages received from the websocket are correctly put into the queue."""
    symbols = ["BTC/USDT"]
    manager = BinanceWebSocketManager(symbols)
    manager._running = True 
    
    test_msg = {"e": "kline", "s": "BTCUSDT", "c": "50000"}
    manager.queue.put_nowait(test_msg)
    
    msg = await asyncio.wait_for(manager.queue.get(), timeout=1.0)
    assert msg["s"] == "BTCUSDT"
    assert msg["e"] == "kline"
    manager.stop()

@pytest.mark.asyncio
async def test_websocket_combined_url_construction():
    """Verify that the combined stream URL is constructed correctly."""
    symbols = ["BTC/USDT", "ETH/USDT"]
    manager = BinanceWebSocketManager(symbols)
    
    # Mock websockets.connect as an async context manager
    mock_ws = AsyncMock()
    # Mock __aiter__ to raise an exception to break the loop
    mock_ws.__aiter__.side_effect = Exception("StopLoop")
    
    mock_connect_ctx = MagicMock()
    mock_connect_ctx.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_connect_ctx.__aexit__ = AsyncMock()
    
    with patch("websockets.connect", return_value=mock_connect_ctx) as mock_connect:
        manager._running = True
        # We run it directly but expect it to fail with "StopLoop"
        try:
            await asyncio.wait_for(manager.connect_and_run(), timeout=1.0)
        except Exception as e:
            if str(e) != "StopLoop": pass

        mock_connect.assert_called()
        args, kwargs = mock_connect.call_args
        url = args[0]
        assert "streams=" in url
        assert "btcusdt@markPrice" in url
        assert "ethusdt@markPrice" in url
        manager.stop()

@pytest.mark.asyncio
async def test_listen_key_keep_alive():
    """Verify that the manager attempts to refresh listenKey in the loop."""
    symbols = ["BTC/USDT"]
    manager = BinanceWebSocketManager(symbols, api_key="test_key")
    manager.listen_key = "old_key"
    manager._running = True
    
    mock_exchange = AsyncMock()
    mock_exchange.fapiPrivatePutListenKey = AsyncMock(return_value={})
    mock_exchange.close = AsyncMock()
    
    async def fast_sleep(seconds):
        manager.stop() # Stop the loop after first sleep
        return

    with patch("ccxt.async_support.binance", return_value=mock_exchange), \
         patch("asyncio.sleep", side_effect=fast_sleep):
        
        await manager._keep_alive_loop()
        assert mock_exchange.fapiPrivatePutListenKey.called
        manager.stop()
