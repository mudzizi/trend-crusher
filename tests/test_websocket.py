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
    
    mock_ws = AsyncMock()
    # 1. Message, 2. CancelledError to stop the inner loop
    mock_ws.recv.side_effect = [
        json.dumps({"e": "kline", "s": "BTCUSDT", "c": "50000"}),
        asyncio.CancelledError() 
    ]
    
    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__.return_value = mock_ws
    
    with patch("websockets.connect", return_value=mock_connect_ctx), \
         patch("asyncio.sleep", AsyncMock()):
        
        connect_task = asyncio.create_task(manager.connect())
        
        try:
            msg = await asyncio.wait_for(manager.get_next_message(), timeout=2.0)
            assert msg["s"] == "BTCUSDT"
        finally:
            manager.stop()
            connect_task.cancel()
            try:
                await asyncio.wait_for(connect_task, timeout=1.0)
            except:
                pass

@pytest.mark.asyncio
async def test_websocket_reconnection_logic():
    """Verify that the manager attempts to reconnect on connection failure."""
    symbols = ["ETH/USDT"]
    manager = BinanceWebSocketManager(symbols)
    
    mock_ws = AsyncMock()
    # 1. Message, 2. Error to trigger reconnection, 3. CancelledError to stop
    mock_ws.recv.side_effect = [
        json.dumps({"e": "markPrice", "s": "ETHUSDT"}),
        Exception("Stream Interrupted"),
        asyncio.CancelledError()
    ]
    
    mock_connect_ctx = AsyncMock()
    mock_connect_ctx.__aenter__.return_value = mock_ws
    
    with patch("websockets.connect") as mock_connect, \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        
        # 1. Conn Fail, 2. Success, 3. Re-connect after Stream Interrupted
        mock_connect.side_effect = [
            Exception("Conn Fail"), 
            mock_connect_ctx, 
            mock_connect_ctx,
            mock_connect_ctx
        ]
        
        connect_task = asyncio.create_task(manager.connect())
        
        try:
            msg = await asyncio.wait_for(manager.get_next_message(), timeout=2.0)
            assert msg["s"] == "ETHUSDT"
            # Wait a tiny bit for the reconnection to happen after "Stream Interrupted"
            await asyncio.sleep(0.1)
            assert mock_connect.call_count >= 2
        finally:
            manager.stop()
            connect_task.cancel()
            try:
                await asyncio.wait_for(connect_task, timeout=1.0)
            except:
                pass

@pytest.mark.asyncio
async def test_websocket_url_construction():
    """Verify that symbols are correctly formatted into the Binance WS URL."""
    symbols = ["BTC/USDT", "ETH/USDT"]
    manager = BinanceWebSocketManager(symbols)
    
    # Expected streams: btcusdt@kline_1h, btcusdt@kline_1m, btcusdt@markPrice, etc.
    assert "btcusdt@kline_1h" in manager.url
    assert "ethusdt@markPrice" in manager.url
    assert "wss://fstream.binance.com/ws/" in manager.url

if __name__ == "__main__":
    pytest.main([__file__])
