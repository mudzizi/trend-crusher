import pytest
from unittest.mock import patch, MagicMock
from src.telegram_utils import TelegramNotifier

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
