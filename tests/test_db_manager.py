import pytest
import os
import sqlite3
import pandas as pd
from src.db_manager import DBManager

@pytest.fixture
def temp_db():
    db_path = "test_trades.db"
    if os.path.exists(db_path): os.remove(db_path)
    db = DBManager(db_path=db_path)
    yield db
    if os.path.exists(db_path): os.remove(db_path)

def test_log_trade_open_and_close(temp_db):
    # 1. 포지션 오픈 기록
    temp_db.log_trade_open("BTC/USDT", "LONG", 50000.0, 0.1, 80.0)
    
    # get_trade_history()는 CLOSED만 가져오므로 직접 쿼리하여 OPEN 상태 확인
    with temp_db._get_connection() as conn:
        history = pd.read_sql_query("SELECT * FROM trades", conn)
        
    assert len(history) == 1
    assert history.iloc[0]['symbol'] == "BTC/USDT"
    assert history.iloc[0]['status'] == "OPEN"
    
    # 2. 포지션 종료 기록
    temp_db.log_trade_close(51000.0, 2.0, 200.0)
    history = temp_db.get_trade_history() # 이제 CLOSED이므로 helper 사용 가능
    assert len(history) == 1
    assert history.iloc[0]['close_price'] == 51000.0
    assert history.iloc[0]['pnl_usdt'] == 200.0
    assert history.iloc[0]['status'] == "CLOSED"

def test_log_equity(temp_db):
    temp_db.log_equity(10000.0)
    temp_db.log_equity(10500.0)
    history = temp_db.get_equity_history()
    assert len(history) == 2
    assert history.iloc[0]['balance'] == 10000.0
    assert history.iloc[1]['balance'] == 10500.0


def test_update_open_trade(temp_db):
    temp_db.log_trade_open("ETH/USDT", "LONG", 2000.0, 1.0, 70.0)
    temp_db.update_open_trade(2025.0, 1.5, 75.0)

    with temp_db._get_connection() as conn:
        history = pd.read_sql_query("SELECT * FROM trades", conn)

    assert len(history) == 1
    assert history.iloc[0]['open_price'] == 2025.0
    assert history.iloc[0]['quantity'] == 1.5
    assert history.iloc[0]['strength'] == 75.0
