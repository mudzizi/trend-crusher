import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync
import asyncio

@pytest.fixture
def mock_config():
    return {
        "SNIPER_PROXIMITY_PCT": 0.01, # 1% proximity for testing
        "VOL_MULTIPLIER": 2.0,
        "ADX_FILTER_LEVEL": 15,
        "EMA_TREND_PERIOD": 100,
        "INITIAL_SL_ATR": 2.0,
        "DRY_RUN": False # Must be False to allow manage_sniper_ambush to execute
    }

@pytest.fixture
def mock_bot(mock_config):
    mock_exchange = MagicMock()
    mock_exchange.create_limit_order = AsyncMock(return_value={'id': 'limit_123'})
    mock_exchange.cancel_order = AsyncMock()
    
    mock_pm = MagicMock()
    mock_pm.calculate_order_qty = AsyncMock(return_value=1.0)
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, MagicMock(), MagicMock())
    bot.settings.update(mock_config)
    bot.use_sniper = True
    
    # Mocking indicator DataFrames
    bot.ohlcv_1h = pd.DataFrame() 
    bot.ohlcv_4h = pd.DataFrame()
    return bot

def setup_mock_indicators(bot, upper=10000, lower=9000, atr=100, avg_vol=1000, adx=20, ema_h=9500, curr_vol=2500):
    """Helper to set up df_indicators for testing check_entry."""
    df = pd.DataFrame([{
        'upper': upper,
        'lower': lower,
        'atr': atr,
        'avg_vol': avg_vol,
        'adx': adx,
        'ema_h': ema_h,
        'volume': curr_vol,
        'close': bot.last_price # Usually last_price is close
    }])
    bot.df_indicators = df

@pytest.mark.asyncio
async def test_sniper_ambush_placed_when_conditions_met(mock_bot):
    # 시나리오: 4대 기둥이 모두 완벽하게 맞을 때 매복(Limit) 실행
    mock_bot.last_price = 9950
    setup_mock_indicators(mock_bot, upper=10000, lower=9000, atr=100, avg_vol=1000, adx=20, ema_h=9500, curr_vol=2500)
    
    # Price 9950 is within 1% of upper 10000 (prox_threshold=0.005 default or 0.01 in mock_config)
    # distance = (10000 - 9950) / 9950 = 0.005 <= 0.01 (OK)
    
    await mock_bot.check_entry()
    
    # Assertions
    assert mock_bot.active_sniper_order_id == 'limit_123'
    mock_bot.exchange.create_limit_order.assert_called_once_with('BTC/USDT', 'buy', 1.0, 10000)

@pytest.mark.asyncio
async def test_sniper_ambush_aborted_when_condition_fails(mock_bot):
    # Scenario: Ambush is active but momentum dies. Should be cancelled immediately.
    mock_bot.active_sniper_order_id = 'limit_123'
    mock_bot.last_price = 9950
    
    # momentum_ok = curr_vol > (avg_vol * vol_mult) -> 500 > (1000 * 2.0) is False
    setup_mock_indicators(mock_bot, curr_vol=500) 
    
    await mock_bot.check_entry()
    
    # In the refactored check_entry, if not (momentum_ok and trend_ok), 
    # it cancels sniper and returns.
    assert mock_bot.active_sniper_order_id is None 
    mock_bot.exchange.cancel_order.assert_called_once_with('limit_123', 'BTC/USDT')

@pytest.mark.asyncio
async def test_sniper_kill_switch_forces_market_order(mock_bot):
    # 시나리오: 스나이퍼 모드를 끄면 매복하지 않고 돌파 시 즉시 시장가 진입
    mock_bot.use_sniper = False
    mock_bot.execute_entry = AsyncMock()
    mock_bot.last_price = 10050 # Breakout!
    
    setup_mock_indicators(mock_bot, upper=10000, curr_vol=2500)
    
    await mock_bot.check_entry()
    
    # Assertions
    mock_bot.execute_entry.assert_called_once_with(1, 100) # Fallback to market
    assert mock_bot.active_sniper_order_id is None
