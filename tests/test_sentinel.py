import pytest
from unittest.mock import MagicMock, patch
from scripts.live_bot_async import SymbolBotAsync, handle_commands
import asyncio

@pytest.fixture
def mock_config():
    return {
        "TELEGRAM_CHAT_ID": "123456",
        "SYMBOLS_LIST": ["BTC/USDT"],
        "DRY_RUN": True,
        "VERSION": "11.1.1-test"
    }

@pytest.mark.asyncio
async def test_sentinel_proposal_and_apply(mock_config):
    # 시나리오: 최적화가 제안 대기열에 들어가고, /apply 명령으로만 반영되는지 확인
    from scripts.live_bot_async import handle_commands
    
    mock_exchange = MagicMock()
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_pm = MagicMock()
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bots = {"btcusdt": bot}
    
    # 1. 최적화 결과가 나왔을 때
    new_settings = {"VOL_MULTIPLIER": 3.0, "ADX_FILTER_LEVEL": 25, "EMA_TREND_PERIOD": 150}
    bot.pending_settings = new_settings
    
    # 2. /apply 명령 수신 모킹
    mock_notifier.get_updates.return_value = {
        "ok": True,
        "result": [{
            "update_id": 100,
            "message": {
                "text": "/apply BTC/USDT",
                "chat": {"id": 123456}
            }
        }]
    }
    
    # 전역 CONFIG 패치 (중요: handle_commands가 이 값을 참조함)
    with patch('scripts.live_bot_async.CONFIG', mock_config), \
         patch('asyncio.sleep', side_effect=asyncio.CancelledError):
        try:
            await handle_commands(bots, mock_notifier, mock_pm)
        except asyncio.CancelledError:
            pass
            
    # 3. 결과 확인
    assert bot.settings["VOL_MULTIPLIER"] == 3.0
    assert bot.pending_settings is None 

@pytest.mark.asyncio
async def test_sentinel_proposal_reject(mock_config):
    # 시나리오: /reject 명령 시 제안이 취소되고 설정이 유지되는지 확인
    from scripts.live_bot_async import handle_commands
    
    mock_exchange = MagicMock()
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_pm = MagicMock()
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bots = {"btcusdt": bot}
    
    original_vol = bot.settings["VOL_MULTIPLIER"]
    bot.pending_settings = {"VOL_MULTIPLIER": 5.0}
    
    mock_notifier.get_updates.return_value = {
        "ok": True,
        "result": [{
            "update_id": 101,
            "message": {
                "text": "/reject BTC/USDT",
                "chat": {"id": 123456}
            }
        }]
    }
    
    with patch('scripts.live_bot_async.CONFIG', mock_config), \
         patch('asyncio.sleep', side_effect=asyncio.CancelledError):
        try:
            await handle_commands(bots, mock_notifier, mock_pm)
        except asyncio.CancelledError:
            pass

    assert bot.settings["VOL_MULTIPLIER"] == original_vol
    assert bot.pending_settings is None
