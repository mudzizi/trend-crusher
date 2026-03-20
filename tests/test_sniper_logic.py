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

@pytest.mark.asyncio
async def test_sniper_ambush_placed_when_conditions_met(mock_bot):
    # 시나리오: 4대 기둥이 모두 완벽하게 맞을 때 매복(Limit) 실행
    with patch('scripts.live_bot_async.calculate_donchian') as mock_dc, \
         patch('scripts.live_bot_async.calculate_atr') as mock_atr, \
         patch('scripts.live_bot_async.calculate_avg_vol') as mock_vol, \
         patch('scripts.live_bot_async.calculate_adx') as mock_adx, \
         patch('scripts.live_bot_async.calculate_ema') as mock_ema:
             
        # Mock indicator values
        mock_dc.return_value = (pd.Series([10000]), pd.Series([9000])) # Upper: 10000
        mock_atr.return_value = pd.Series([100])
        mock_vol.return_value = pd.Series([1000]) # Avg Vol
        mock_adx.return_value = pd.Series([20])   # ADX > 15 (OK)
        mock_ema.return_value = pd.Series([9500]) # EMA < Price (OK for Long)
        
        # Mock dataframe volume
        mock_bot.ohlcv_1h = pd.DataFrame({'volume': [2500]}) # Vol > 2000 (OK)
        
        # Price is at 9950. Distance to 10000 is 50 / 9950 = 0.005 < 0.01 (OK)
        mock_bot.last_price = 9950
        
        await mock_bot.check_entry()
        
        # Assertions
        assert mock_bot.active_sniper_order_id == 'limit_123'
        mock_bot.exchange.create_limit_order.assert_called_once_with('BTC/USDT', 'buy', 1.0, 10000)

@pytest.mark.asyncio
async def test_sniper_ambush_aborted_when_condition_fails(mock_bot):
    # 시나리오: 매복 중인데 거래량이 죽어버리면(Volume Drop) 즉시 취소
    mock_bot.active_sniper_order_id = 'limit_123'
    
    with patch('scripts.live_bot_async.calculate_donchian') as mock_dc, \
         patch('scripts.live_bot_async.calculate_atr') as mock_atr, \
         patch('scripts.live_bot_async.calculate_avg_vol') as mock_vol, \
         patch('scripts.live_bot_async.calculate_adx') as mock_adx, \
         patch('scripts.live_bot_async.calculate_ema') as mock_ema:
             
        mock_dc.return_value = (pd.Series([10000]), pd.Series([9000]))
        mock_atr.return_value = pd.Series([100])
        mock_vol.return_value = pd.Series([1000])
        mock_adx.return_value = pd.Series([20])
        mock_ema.return_value = pd.Series([9500])
        
        # Sudden Volume Drop! Now 1500 < (1000 * 2.0)
        mock_bot.ohlcv_1h = pd.DataFrame({'volume': [1500]}) 
        mock_bot.last_price = 9950
        
        await mock_bot.check_entry()
        
        # Assertions
        assert mock_bot.active_sniper_order_id is None # Cancelled
        mock_bot.exchange.cancel_order.assert_called_once_with('limit_123', 'BTC/USDT')

@pytest.mark.asyncio
async def test_sniper_kill_switch_forces_market_order(mock_bot):
    # 시나리오: 스나이퍼 모드를 끄면 매복하지 않고 돌파 시 즉시 시장가 진입
    mock_bot.use_sniper = False
    mock_bot.execute_entry = AsyncMock()
    
    with patch('scripts.live_bot_async.calculate_donchian') as mock_dc, \
         patch('scripts.live_bot_async.calculate_atr') as mock_atr, \
         patch('scripts.live_bot_async.calculate_avg_vol') as mock_vol, \
         patch('scripts.live_bot_async.calculate_adx') as mock_adx, \
         patch('scripts.live_bot_async.calculate_ema') as mock_ema:
             
        mock_dc.return_value = (pd.Series([10000]), pd.Series([9000]))
        mock_atr.return_value = pd.Series([100])
        mock_vol.return_value = pd.Series([1000])
        mock_adx.return_value = pd.Series([20])
        mock_ema.return_value = pd.Series([9500])
        mock_bot.ohlcv_1h = pd.DataFrame({'volume': [2500]})
        
        # Price is 10050 (Breakout occurred!)
        mock_bot.last_price = 10050
        
        await mock_bot.check_entry()
        
        # Assertions
        mock_bot.execute_entry.assert_called_once_with(1, 100) # Fallback to market
        assert mock_bot.active_sniper_order_id is None
