import pytest
import os
import pandas as pd
from unittest.mock import MagicMock, patch
from src.portfolio_manager import PortfolioManager
from src.db_manager import DBManager
from scripts.live_bot_multi import SymbolBot

@pytest.fixture
def clean_db():
    db_path = "test_isolated.db"
    if os.path.exists(db_path): os.remove(db_path)
    db = DBManager(db_path=db_path)
    yield db
    if os.path.exists(db_path): os.remove(db_path)

def test_capital_isolation_logic(clean_db):
    # 시나리오: TRUMP는 돈을 벌었고, ETH는 처음 시작함. 
    # ETH의 수량 계산은 자신의 ALLOCATED_SEED를 기준으로만 이루어져야 함.
    
    config = {
        "DRY_RUN": True,
        "SYMBOL_SETTINGS": {
            "TRUMP/USDT": {"ALLOCATED_SEED": 4000.0, "RISK_PER_TRADE": 0.02},
            "ETH/USDT": {"ALLOCATED_SEED": 2500.0, "RISK_PER_TRADE": 0.02}
        },
        "MAX_CONCURRENT_TRADES": 3,
        "MAX_LEVERAGE": 5
    }
    
    mock_exchange = MagicMock()
    pm = PortfolioManager(mock_exchange, config)
    pm.db = clean_db # Use our clean test DB
    
    # 1. TRUMP가 수익을 내서 잔고가 늘어남
    clean_db.log_equity(4000.0, symbol='TRUMP/USDT')
    clean_db.log_equity(5000.0, symbol='TRUMP/USDT') # $1000 수익
    
    # 2. ETH는 아직 기록이 없음 (초기 상태)
    
    # 3. ETH 수량 계산 시도
    # Price: 2000, SL: 1900 (Dist: 100)
    # Expected Risk Qty: (2500 * 0.02) / 100 = 0.5
    # 만약 격리가 안 되었다면 전체 잔고나 TRUMP 잔고가 섞여서 다른 값이 나올 것임.
    qty = pm.calculate_order_qty("ETH/USDT", 2000, 1900)
    
    assert qty == 0.5
    assert pm.get_total_equity("ETH/USDT") == 2500.0
    assert pm.get_total_equity("TRUMP/USDT") == 5000.0

@patch('scripts.live_bot_multi.TelegramNotifier')
@patch('src.visualizer.TradingVisualizer')
def test_smart_margin_setup_safety_in_dry_run(mock_viz, mock_notifier, clean_db):
    # 시나리오: DRY_RUN 모드에서는 어떠한 마진 설정 API도 호출되지 않아야 함 (안전 제일)
    mock_exchange = MagicMock()
    
    # settings에 DRY_RUN이 True인 상태로 봇 생성
    bot = SymbolBot("BTC/USDT", mock_exchange, MagicMock(), mock_notifier, clean_db, mock_viz)
    
    # DRY_RUN 가드에 의해 fetch_positions와 set_margin_mode 모두 호출되지 않았어야 함
    mock_exchange.fetch_positions.assert_not_called()
    mock_exchange.set_margin_mode.assert_not_called()
    
    bot.logger.info("✅ Verified: No exchange interaction in DRY_RUN mode.")

if __name__ == "__main__":
    pytest.main([__file__])
