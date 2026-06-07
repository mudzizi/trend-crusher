import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from scripts.live_bot_async import SymbolBotAsync

def test_get_detailed_status_idle_no_indicators():
    mock_exchange = MagicMock()
    mock_pm = MagicMock()
    mock_notifier = MagicMock()
    mock_db = MagicMock()
    
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.last_price = 50000.0
        bot.df_indicators = None
        
        status = bot.get_detailed_status()
        assert "BTC/USDT" in status
        assert "IDLE" in status
        assert "Indicator Data: N/A" in status

def test_get_detailed_status_idle_with_indicators():
    mock_exchange = MagicMock()
    mock_pm = MagicMock()
    mock_notifier = MagicMock()
    mock_db = MagicMock()
    
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.last_price = 50000.0
        bot.df_indicators = pd.DataFrame([{
            'ema_h': 49000.0,
            'upper': 51000.0,
            'lower': 48000.0,
            'volume': 150.0,
            'avg_vol': 100.0,
            'adx': 25.0,
            'adx_4h': 20.0,
            'chop': 50.0,
            'chaos': 10.0,
            'squeeze': 0.0,
            'ema_slope': 1.5
        }])
        
        status = bot.get_detailed_status()
        assert "BTC/USDT" in status
        assert "IDLE" in status
        assert "BULL 🚀" in status
        assert "Volume (1h): 150.0" in status
        assert "ADX (1h): 25.0" in status
        assert "EMA Slope: +1.5000" in status

def test_get_detailed_status_long_position():
    mock_exchange = MagicMock()
    mock_pm = MagicMock()
    mock_notifier = MagicMock()
    mock_db = MagicMock()
    
    with patch('scripts.live_bot_async.TrendCrusherV2'):
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.position = 1 # LONG
        bot.entry_price = 48000.0
        bot.quantity = 0.5
        bot.sl_price = 47000.0
        bot.last_price = 50000.0
        
        bot.df_indicators = pd.DataFrame([{
            'ema_h': 49000.0,
            'upper': 51000.0,
            'lower': 48000.0,
            'volume': 150.0,
            'avg_vol': 100.0,
            'adx': 25.0,
            'adx_4h': 20.0,
            'chop': 50.0,
            'chaos': 10.0,
            'squeeze': 0.0,
            'ema_slope': 1.5
        }])
        
        status = bot.get_detailed_status()
        assert "BTC/USDT" in status
        assert "LONG 🟢" in status
        assert "진입가: 48,000.00" in status
        assert "수량: 0.5000" in status
        assert "손절가: 47,000.00" in status
        assert "현재 PnL: +4.17%" in status
