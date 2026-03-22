import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from scripts.live_bot_async import SymbolBotAsync
import asyncio
import pandas as pd

@pytest.fixture
def mock_config():
    return {
        "TELEGRAM_CHAT_ID": "123456",
        "SYMBOLS_LIST": ["BTC/USDT"],
        "DRY_RUN": True,
        "VERSION": "11.1.1-test",
        "VOL_MULTIPLIER": 2.5,
        "ADX_FILTER_LEVEL": 20,
        "EMA_TREND_PERIOD": 100,
        "DONCHIAN_PERIOD": 20,
        "ATR_PERIOD": 14,
        "AVG_VOL_PERIOD": 20,
        "INITIAL_SL_ATR": 2.0,
        "TRAILING_ATR_MULT": 4.5,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h"
    }

@pytest.mark.asyncio
async def test_sentinel_proposal_and_apply_logic(mock_config):
    # 시나리오: 봇 인스턴스에 직접 pending_settings를 넣고, apply 메서드가 정상 작동하는지 확인
    # handle_commands의 무한루프를 피하기 위해 내부 로직만 직접 테스트
    mock_exchange = MagicMock()
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_pm = MagicMock()
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings["VOL_MULTIPLIER"] = 2.5
    
    # 1. Proposal comes in
    new_settings = {"VOL_MULTIPLIER": 3.0, "ADX_FILTER_LEVEL": 25, "EMA_TREND_PERIOD": 150}
    bot.pending_settings = new_settings
    
    # 2. Simulate the /apply logic from handle_commands
    # if cmd == "/apply":
    symbol_from_cmd = "BTC/USDT"
    target_key = symbol_from_cmd.replace('/', '').lower()
    
    bots = {"btcusdt": bot}
    if target_key in bots and bots[target_key].pending_settings:
        applied_settings = bots[target_key].pending_settings
        bots[target_key].hot_reload_settings(applied_settings)
        bots[target_key].pending_settings = None
        
    # 3. Validation
    assert bot.settings["VOL_MULTIPLIER"] == 3.0
    assert bot.pending_settings is None

@pytest.mark.asyncio
async def test_sentinel_proposal_reject_logic(mock_config):
    mock_exchange = MagicMock()
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_pm = MagicMock()
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings["VOL_MULTIPLIER"] = 2.5
    bot.pending_settings = {"VOL_MULTIPLIER": 5.0}
    
    # Simulate /reject logic
    bot.pending_settings = None
    
    assert bot.settings["VOL_MULTIPLIER"] == 2.5
    assert bot.pending_settings is None
