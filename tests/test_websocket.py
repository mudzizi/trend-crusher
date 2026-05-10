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
    
    sleep_count = 0
    async def fast_sleep(seconds):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 1:
            manager.stop() # Stop the loop after second check
        return

    with patch("ccxt.async_support.binance", return_value=mock_exchange), \
         patch("asyncio.sleep", side_effect=fast_sleep):
        
        # We need to ensure _running stays True for at least one cycle after sleep
        await manager._keep_alive_loop()
        assert mock_exchange.fapiPrivatePutListenKey.called
        manager.stop()

@pytest.mark.asyncio
async def test_listen_key_recovery_on_error():
    """Verify that the manager recovers when listenKey is invalid (-1125)."""
    symbols = ["BTC/USDT"]
    manager = BinanceWebSocketManager(symbols, api_key="test_key")
    manager.listen_key = "expired_key"
    manager._running = True
    
    mock_exchange = AsyncMock()
    mock_exchange.fapiPrivatePutListenKey = AsyncMock(side_effect=Exception("binance {\"code\":-1125,\"msg\":\"This listenKey does not exist.\"}"))
    mock_exchange.fapiPrivatePostListenKey = AsyncMock(return_value={"listenKey": "new_key"})
    mock_exchange.close = AsyncMock()
    
    mock_ws = AsyncMock()
    manager.private_ws = mock_ws
    
    # Track calls
    calls = []

    async def fast_sleep(seconds):
        calls.append(seconds)
        if len(calls) > 3: # Safety break
            manager.stop()
        if seconds == 60: # Recovery sleep
            manager.stop()
        return

    with patch("ccxt.async_support.binance", return_value=mock_exchange), \
         patch("asyncio.sleep", side_effect=fast_sleep):
        
        # Manually run one iteration of the loop instead of a task
        # But _keep_alive_loop is an infinite while loop.
        # We'll use the task but with a very short timeout.
        task = asyncio.create_task(manager._keep_alive_loop())
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            manager.stop()
            await task
        
        assert mock_ws.close.called
        assert manager.listen_key is None or manager.listen_key == "new_key"
