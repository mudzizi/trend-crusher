import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.websocket_manager import BinanceWebSocketManager

@pytest.mark.asyncio
async def test_websocket_message_queuing():
    """Verify that messages received from the websocket are correctly put into the queue."""
    symbols = ["BTC/USDT"]
    # Mocking in the correct module path
    with patch("src.websocket_manager.UMFuturesWebsocketClient") as mock_ws_client:
        manager = BinanceWebSocketManager(symbols)
        manager._running = True 
        
        test_msg = json.dumps({"e": "kline", "s": "BTCUSDT", "c": "50000"})
        manager._on_message(None, test_msg)
        
        msg = await asyncio.wait_for(manager.queue.get(), timeout=1.0)
        assert msg["s"] == "BTCUSDT"
        assert msg["e"] == "kline"
        manager.stop()

@pytest.mark.asyncio
async def test_websocket_initialization():
    """Verify that the manager initializes the official client correctly."""
    symbols = ["ETH/USDT"]
    with patch("src.websocket_manager.UMFuturesWebsocketClient") as mock_ws_client:
        manager = BinanceWebSocketManager(symbols)
        await manager.connect()
        
        mock_ws_client.assert_called_once()
        instance = mock_ws_client.return_value
        instance.kline.assert_any_call(symbol="ethusdt", interval="1h")
        instance.mark_price.assert_any_call(symbol="ethusdt", speed=1)
        manager.stop()

@pytest.mark.asyncio
async def test_listen_key_refresh_on_failure():
    """Verify that the manager attempts to refresh listenKey when keep-alive fails."""
    symbols = ["BTC/USDT"]
    manager = BinanceWebSocketManager(symbols, api_key="test_key")
    
    # Properly mock CCXT async methods
    mock_exchange = AsyncMock()
    mock_exchange.fapiPrivatePutListenKey.side_effect = Exception("Expired")
    mock_exchange.close = AsyncMock() # Crucial fix for await expression error
    
    with patch.object(BinanceWebSocketManager, "_get_new_listen_key", AsyncMock(return_value="new_key")), \
         patch.object(BinanceWebSocketManager, "_refresh_user_data_stream", AsyncMock()) as mock_refresh, \
         patch("src.websocket_manager.UMFuturesWebsocketClient"), \
         patch("ccxt.async_support.binance", return_value=mock_exchange):
        
        with patch("asyncio.sleep", AsyncMock()):
            manager.listen_key = "old_key"
            manager._running = True
            
            try:
                await asyncio.wait_for(manager._keep_alive_loop(), timeout=0.5)
            except (asyncio.TimeoutError, asyncio.CancelledError, StopIteration):
                pass
            
            mock_refresh.assert_called()
            manager.stop()

if __name__ == "__main__":
    pytest.main([__file__])
