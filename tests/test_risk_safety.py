import pytest
import pandas as pd
from unittest.mock import MagicMock
import scripts.live_bot as live_bot_module
from scripts.live_bot import TrendCrusherLive

@pytest.fixture
def mock_bot():
    # 실제 API 키 없이 봇 객체 생성 (MagicMock 사용)
    config = {
        "BINANCE_API_KEY": "test",
        "BINANCE_SECRET": "test",
        "SYMBOL": "TRUMP/USDT",
        "SEED": 1000.0,
        "RISK_PER_TRADE": 0.02,
        "MAX_LEVERAGE": 5.0,
        "DRY_RUN": True
    }
    
    # 봇의 __init__에서 발생하는 API 호출들을 모킹
    TrendCrusherLive.fetch_data = MagicMock()
    TrendCrusherLive.calculate_indicators = MagicMock()
    
    bot = TrendCrusherLive()
    bot.session_capital = 1000.0 # 초기 자산 1000 USDT
    
    # 바이낸스 마켓 정보 모킹 (TRUMP/USDT 기준)
    bot.exchange.market = MagicMock(return_value={
        'symbol': 'TRUMP/USDT',
        'precision': {'amount': 1, 'price': 3}, # 수량 소수점 1자리, 가격 3자리
        'limits': {
            'amount': {'min': 0.1, 'max': 100000.0},
            'cost': {'min': 5.0}
        }
    })
    
    # amount_to_precision 모킹 (실제 ccxt 함수처럼 작동하게 함)
    bot.exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{float(a):.1f}")
    bot.db.log_trade_open = MagicMock()
    bot.db.update_open_trade = MagicMock()
    bot.notifier.notify_entry = MagicMock()
    bot.notifier.notify_status = MagicMock()
    
    return bot

def test_leverage_cap_safety(mock_bot):
    # 시나리오: 손절폭이 매우 좁아서 계산된 수량이 자산을 훨씬 초과하는 경우
    price = 10.0
    mock_bot.sl_price = 9.99 # 손절폭이 0.1%로 매우 좁음
    
    # 리스크(20 USDT) / 손절폭(0.01) = 2000개 주문 시도 (20000 USDT 규모, 레버리지 20배)
    # 하지만 MAX_LEVERAGE가 5이므로 최대 5000 USDT 규모(500개)로 제한되어야 함
    
    mock_bot.execute_order(1, price)
    
    # 결과 확인: 2000개가 아닌 500개 근처(레버리지 5배 수준)여야 함
    assert mock_bot.quantity <= 500.0
    assert mock_bot.quantity > 0

def test_precision_rounding(mock_bot):
    # 시나리오: 수량이 소수점 지저분하게 계산되는 경우
    price = 10.0
    mock_bot.sl_price = 9.5
    # Risk 20 / Stop 0.5 = 40.0
    # 만약 수량이 40.12345라면 40.1로 반올림되어야 함
    
    mock_bot.execute_order(1, price)
    
    # 문자열로 변환했을 때 소수점 1자리까지만 있는지 확인
    qty_str = str(mock_bot.quantity)
    if '.' in qty_str:
        assert len(qty_str.split('.')[1]) <= 1

def test_min_quantity_adjustment(mock_bot):
    # 시나리오: 자산이 너무 적어 계산된 수량이 최소 주문 단위(0.1)보다 작은 경우
    mock_bot.session_capital = 10.0 # 자산이 10 USDT뿐임
    price = 10.0
    mock_bot.sl_price = 8.0
    # Risk 0.2 / Stop 2.0 = 0.1
    # 만약 0.05가 계산된다면 0.1로 올려주거나 경고를 띄워야 함
    
    mock_bot.execute_order(1, price)
    assert mock_bot.quantity >= 0.1


def test_live_split_fill_updates_average_entry(mock_bot):
    previous_split_count = live_bot_module.CONFIG["ENTRY_SPLIT_COUNT"]
    live_bot_module.CONFIG["ENTRY_SPLIT_COUNT"] = 2
    try:
        opened_at = pd.Timestamp("2024-03-16 12:00:00")
        mock_bot._record_entry_fill(1, 100.0, 1.0, 0.0, opened_at, 50.0, is_add=False)
        mock_bot._record_entry_fill(1, 110.0, 1.0, 1.0, opened_at + pd.Timedelta(hours=1), 55.0, is_add=True)

        assert mock_bot.quantity == 2.0
        assert mock_bot.entry_price == pytest.approx(105.0)
        assert mock_bot.splits_filled == 2
        mock_bot.db.update_open_trade.assert_called_once()
    finally:
        live_bot_module.CONFIG["ENTRY_SPLIT_COUNT"] = previous_split_count


def test_live_split_only_triggers_after_next_signal_bar(mock_bot):
    previous_split_count = live_bot_module.CONFIG["ENTRY_SPLIT_COUNT"]
    live_bot_module.CONFIG["ENTRY_SPLIT_COUNT"] = 2
    try:
        opened_at = pd.Timestamp("2024-03-16 12:00:00")
        mock_bot.position = 1
        mock_bot.splits_filled = 1
        mock_bot.next_split_time = opened_at + pd.Timedelta(hours=1)

        assert mock_bot._can_add_split(opened_at, 101.0, 100.0) is False
        assert mock_bot._can_add_split(opened_at + pd.Timedelta(hours=1), 101.0, 100.0) is True
        assert mock_bot._can_add_split(opened_at + pd.Timedelta(hours=1), 99.0, 100.0) is False
    finally:
        live_bot_module.CONFIG["ENTRY_SPLIT_COUNT"] = previous_split_count


def test_execute_order_uses_actual_fill_from_order_response(mock_bot):
    previous_dry_run = live_bot_module.CONFIG["DRY_RUN"]
    live_bot_module.CONFIG["DRY_RUN"] = False
    mock_bot.sl_price = 9.5
    mock_bot.exchange.has = {"fetchOrder": False}
    mock_bot.exchange.set_leverage = MagicMock()
    mock_bot.exchange.create_market_order = MagicMock(return_value={
        "id": "abc",
        "average": 10.2,
        "filled": 40.0,
        "cost": 408.0,
    })
    try:
        fill = mock_bot.execute_order(1, 10.0)
        assert fill["success"] is True
        assert fill["price"] == pytest.approx(10.2)
        assert fill["quantity"] == pytest.approx(40.0)
        assert mock_bot.quantity == pytest.approx(40.0)
    finally:
        live_bot_module.CONFIG["DRY_RUN"] = previous_dry_run


def test_execute_order_refreshes_fill_from_fetch_order(mock_bot):
    previous_dry_run = live_bot_module.CONFIG["DRY_RUN"]
    live_bot_module.CONFIG["DRY_RUN"] = False
    mock_bot.sl_price = 9.5
    mock_bot.exchange.has = {"fetchOrder": True}
    mock_bot.exchange.set_leverage = MagicMock()
    mock_bot.exchange.create_market_order = MagicMock(return_value={
        "id": "abc",
        "average": None,
        "filled": None,
        "cost": None,
    })
    mock_bot.exchange.fetch_order = MagicMock(return_value={
        "id": "abc",
        "average": 10.1,
        "filled": 39.5,
        "cost": 398.95,
    })
    try:
        fill = mock_bot.execute_order(1, 10.0)
        assert fill["success"] is True
        assert fill["price"] == pytest.approx(10.1)
        assert fill["quantity"] == pytest.approx(39.5)
        mock_bot.exchange.fetch_order.assert_called_once_with("abc", mock_bot.symbol)
    finally:
        live_bot_module.CONFIG["DRY_RUN"] = previous_dry_run
