import pytest
import json
from unittest.mock import MagicMock, patch
from src.telegram_utils import TelegramNotifier

@pytest.fixture
def notifier():
    with patch('src.telegram_utils.CONFIG', {
        "TELEGRAM_TOKEN": "12345:mock_token",
        "TELEGRAM_CHAT_ID": "67890",
        "DRY_RUN": False # Force False for baseline tests
    }):
        return TelegramNotifier()

def test_set_commands_payload(notifier):
    # setMyCommands API 호출 시 올바른 JSON 페이로드를 보내는지 확인
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        notifier.set_commands()
        
        # post 호출 확인
        assert mock_post.called
        args, kwargs = mock_post.call_args
        
        # URL 확인
        assert "setMyCommands" in args[0]
        
        # 명령어 리스트 확인
        commands = kwargs['json']['commands']
        assert any(c['command'] == 'status' for c in commands)
        assert any(c['command'] == 'close_all' for c in commands)

def test_send_message_with_buttons(notifier):
    # 버튼(reply_markup)이 포함된 메시지 전송 시 JSON 구조 확인
    reply_markup = {
        "keyboard": [[{"text": "/status"}]],
        "resize_keyboard": True
    }
    
    with patch('src.telegram_utils.CONFIG', {"DRY_RUN": False}):
        with patch('requests.post') as mock_post:
            notifier.send_message("Hello with buttons", reply_markup=reply_markup)
            
            assert mock_post.called
            args, kwargs = mock_post.call_args
            
            # payload 확인
            payload = kwargs['json']
            assert payload['chat_id'] == "67890"
            assert payload['text'] == "Hello with buttons"
            assert payload['reply_markup'] == reply_markup
            assert "parse_mode" in payload

def test_send_message_dry_run_tag():
    # DRY_RUN 설정 시 [TEST] 태그가 붙는지 확인
    with patch('src.telegram_utils.CONFIG', {
        "TELEGRAM_TOKEN": "12345:token",
        "TELEGRAM_CHAT_ID": "67890",
        "DRY_RUN": True # DRY_RUN ON
    }):
        notifier = TelegramNotifier()
        with patch('requests.post') as mock_post:
            notifier.send_message("Real Message")
            args, kwargs = mock_post.call_args
            assert "[TEST]" in kwargs['json']['text']

if __name__ == "__main__":
    pytest.main([__file__])
