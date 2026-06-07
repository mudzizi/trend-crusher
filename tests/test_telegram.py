import pytest
import json
import pandas as pd
from unittest.mock import patch, MagicMock
from src.telegram_utils import TelegramNotifier
from scripts.live_bot_async import SymbolBotAsync

@pytest.fixture
def notifier():
    with patch('src.telegram_utils.CONFIG', {
        "TELEGRAM_TOKEN": "test_token",
        "TELEGRAM_CHAT_ID": "test_chat_id",
        "DRY_RUN": True
    }):
        return TelegramNotifier()

@patch('requests.post')
def test_send_message(mock_post, notifier):
    notifier.send_message("Test message")
    assert mock_post.called
    args, kwargs = mock_post.call_args
    assert "test_token" in args[0]
    payload = kwargs['json']
    assert payload['chat_id'] == "test_chat_id"
    assert "Test message" in payload['text']

@patch('requests.post')
def test_notify_entry(mock_post, notifier):
    notifier.notify_entry("LONG", 50000.0, 49000.0, 85.0)
    assert mock_post.called
    msg = mock_post.call_args[1]['json']['text']
    assert "LONG" in msg
    assert "50,000" in msg
    assert "49,000" in msg

@patch('requests.post')
def test_notify_exit(mock_post, notifier):
    notifier.notify_exit("AUTO_EXIT", 51000.0, 2.0, 200.0)
    assert mock_post.called
    msg = mock_post.call_args[1]['json']['text']
    assert "51,000" in msg
    assert "+2.00%" in msg
    assert "+200.00 USDT" in msg

# --- From test_telegram_buttons.py ---
def test_set_commands_payload(notifier):
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        notifier.set_commands()
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert "setMyCommands" in args[0]
        commands = kwargs['json']['commands']
        assert any(c['command'] == 'status' for c in commands)
        assert any(c['command'] == 'close_all' for c in commands)

def test_send_message_with_buttons(notifier):
    reply_markup = {
        "keyboard": [[{"text": "/status"}]],
        "resize_keyboard": True
    }
    with patch('src.telegram_utils.CONFIG', {"DRY_RUN": False}):
        with patch('requests.post') as mock_post:
            notifier.send_message("Hello with buttons", reply_markup=reply_markup)
            assert mock_post.called
            args, kwargs = mock_post.call_args
            payload = kwargs['json']
            assert payload['chat_id'] == "test_chat_id"
            assert payload['text'] == "Hello with buttons"
            assert payload['reply_markup'] == reply_markup
            assert "parse_mode" in payload

def test_send_message_dry_run_tag():
    with patch('src.telegram_utils.CONFIG', {
        "TELEGRAM_TOKEN": "12345:token",
        "TELEGRAM_CHAT_ID": "67890",
        "DRY_RUN": True
    }):
        notifier = TelegramNotifier()
        with patch('requests.post') as mock_post:
            notifier.send_message("Real Message")
            args, kwargs = mock_post.call_args
            assert "[TEST]" in kwargs['json']['text']

# --- From test_telegram_status.py ---
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
        bot.position = 1
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
