import pytest
import os
import sqlite3
import pandas as pd
from src.db_manager import DBManager
from src.async_db_manager import AsyncDBManager

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
    temp_db.log_trade_close("BTC/USDT", 51000.0, 2.0, 200.0)
    history = temp_db.get_trade_history() # 이제 CLOSED이므로 helper 사용 가능
    assert len(history) == 1
    assert history.iloc[0]['close_price'] == 51000.0
    assert history.iloc[0]['pnl_usdt'] == 200.0
    assert history.iloc[0]['status'] == "CLOSED"

def test_log_equity(temp_db):
    # 1. 다양한 심볼로 잔고 기록
    temp_db.log_equity(10000.0, symbol='TOTAL')
    temp_db.log_equity(4000.0, symbol='TRUMP/USDT')
    temp_db.log_equity(4200.0, symbol='TRUMP/USDT')
    temp_db.log_equity(2500.0, symbol='ETH/USDT')

    # 2. 전체 기록 확인
    total_history = temp_db.get_equity_history()
    assert len(total_history) == 4

    # 3. 특정 심볼 필터링 확인
    trump_history = temp_db.get_equity_history(symbol='TRUMP/USDT')
    assert len(trump_history) == 2
    assert trump_history.iloc[0]['balance'] == 4000.0
    assert trump_history.iloc[1]['balance'] == 4200.0

    eth_history = temp_db.get_equity_history(symbol='ETH/USDT')
    assert len(eth_history) == 1
    assert eth_history.iloc[0]['balance'] == 2500.0


DB_TEST_PATH = "test_async_trades.db"

@pytest.fixture
def async_db_manager():
    # Setup test DB
    manager = AsyncDBManager(db_path=DB_TEST_PATH)
    yield manager
    # Teardown test DB
    if os.path.exists(DB_TEST_PATH):
        try:
            os.remove(DB_TEST_PATH)
        except Exception as e:
            print(f"Error removing test DB: {e}")

@pytest.mark.asyncio
async def test_async_db_bot_state_operations(async_db_manager):
    # 1. Test saving state asynchronously
    symbol = "BTC/USDT"
    await async_db_manager.save_bot_state(
        symbol=symbol,
        position=1,
        entry_price=65000.0,
        quantity=0.05,
        max_price=66000.0,
        min_price=64000.0,
        sl_price=63000.0,
        sl_order_id="SL12345",
        sniper_id="SNIPER123",
        retest_id="RETEST123"
    )

    # 2. Test retrieving state asynchronously
    state = await async_db_manager.get_bot_state(symbol)
    assert state is not None
    assert state['symbol'] == symbol
    assert int(state['position']) == 1
    assert float(state['entry_price']) == 65000.0
    assert float(state['quantity']) == 0.05
    assert float(state['max_price']) == 66000.0
    assert float(state['min_price']) == 64000.0
    assert float(state['sl_price']) == 63000.0
    assert state['sl_order_id'] == "SL12345"
    assert state['sniper_order_id'] == "SNIPER123"
    assert state['retest_order_id'] == "RETEST123"

@pytest.mark.asyncio
async def test_async_db_trade_log_operations(async_db_manager):
    symbol = "ETH/USDT"
    # 1. Test log trade open
    await async_db_manager.log_trade_open(symbol, "LONG", 3500.0, 1.5, 100.0)
    
    # Verify open trade exists
    active_trades = await async_db_manager.get_active_trades()
    assert not active_trades.empty
    trade_row = active_trades[active_trades['symbol'] == symbol]
    assert len(trade_row) == 1
    assert trade_row.iloc[0]['side'] == "LONG"
    assert float(trade_row.iloc[0]['open_price']) == 3500.0
    assert float(trade_row.iloc[0]['quantity']) == 1.5

    # 2. Test log trade close
    await async_db_manager.log_trade_close(symbol, 3600.0, 2.85, 150.0)

    # Verify no open trades remain
    active_trades_after = await async_db_manager.get_active_trades()
    assert active_trades_after[active_trades_after['symbol'] == symbol].empty

    # Verify trade is archived in trade history
    history = await async_db_manager.get_trade_history()
    assert not history.empty
    archived_row = history[history['symbol'] == symbol]
    assert len(archived_row) == 1
    assert archived_row.iloc[0]['status'] == "CLOSED"
    assert float(archived_row.iloc[0]['close_price']) == 3600.0
    assert float(archived_row.iloc[0]['pnl_usdt']) == 150.0

def test_log_history_1h_batch(temp_db):
    symbol = "XRP/USDT"
    records = [
        {
            'timestamp': '2026-06-13 12:00:00',
            'close': 1.10,
            'ema': 1.05,
            'd_upper': 1.20,
            'd_lower': 1.00,
            'volume': 10000.0,
            'adx': 25.0,
            'chaos': 15.0,
            'squeeze': 1.0,
            'slope': 0.01,
            'chop': 30.0,
            'adx_4h': 18.0
        },
        {
            'timestamp': '2026-06-13 13:00:00',
            'close': 1.12,
            'ema': 1.06,
            'd_upper': 1.21,
            'd_lower': 1.01,
            'volume': 12000.0,
            'adx': 26.0,
            'chaos': 16.0,
            'squeeze': 0.0,
            'slope': 0.02,
            'chop': 31.0,
            'adx_4h': 19.0
        }
    ]
    
    # Write batch
    temp_db.log_history_1h_batch(symbol, records)
    
    # Read back and assert
    history = temp_db.get_history_1h(symbol, limit=10)
    assert len(history) == 2
    
    assert history.iloc[0]['timestamp'] == '2026-06-13 12:00:00'
    assert history.iloc[0]['adx_4h'] == 18.0
    assert history.iloc[1]['timestamp'] == '2026-06-13 13:00:00'
    assert history.iloc[1]['adx_4h'] == 19.0
    
    # Test replacement (overwriting)
    updated_records = [
        {
            'timestamp': '2026-06-13 12:00:00',
            'close': 1.10,
            'ema': 1.05,
            'd_upper': 1.20,
            'd_lower': 1.00,
            'volume': 10000.0,
            'adx': 25.0,
            'chaos': 15.0,
            'squeeze': 1.0,
            'slope': 0.01,
            'chop': 30.0,
            'adx_4h': 45.0
        }
    ]
    temp_db.log_history_1h_batch(symbol, updated_records)
    
    history_after = temp_db.get_history_1h(symbol, limit=10)
    assert len(history_after) == 2
    row_12 = history_after[history_after['timestamp'] == '2026-06-13 12:00:00']
    assert len(row_12) == 1
    assert row_12.iloc[0]['adx_4h'] == 45.0

@pytest.mark.asyncio
async def test_async_log_history_1h_batch(async_db_manager):
    symbol = "TRUMP/USDT"
    records = [
        {
            'timestamp': '2026-06-13 14:00:00',
            'close': 2.20,
            'ema': 2.10,
            'd_upper': 2.30,
            'd_lower': 2.00,
            'volume': 50000.0,
            'adx': 35.0,
            'chaos': 25.0,
            'squeeze': 0.0,
            'slope': 0.05,
            'chop': 40.0,
            'adx_4h': 28.0
        }
    ]
    await async_db_manager.log_history_1h_batch(symbol, records)
    
    history = await async_db_manager.get_history_1h(symbol, limit=10)
    assert len(history) == 1
    assert history.iloc[0]['timestamp'] == '2026-06-13 14:00:00'
    assert history.iloc[0]['adx_4h'] == 28.0
