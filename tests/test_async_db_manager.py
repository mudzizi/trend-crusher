import pytest
import os
import asyncio
from src.async_db_manager import AsyncDBManager

DB_TEST_PATH = "test_async_trades.db"

@pytest.fixture
def db_manager():
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
async def test_async_db_bot_state_operations(db_manager):
    # 1. Test saving state asynchronously
    symbol = "BTC/USDT"
    await db_manager.save_bot_state(
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
    state = await db_manager.get_bot_state(symbol)
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
async def test_async_db_trade_log_operations(db_manager):
    symbol = "ETH/USDT"
    # 1. Test log trade open
    await db_manager.log_trade_open(symbol, "LONG", 3500.0, 1.5, 100.0)
    
    # Verify open trade exists
    active_trades = await db_manager.get_active_trades()
    assert not active_trades.empty
    trade_row = active_trades[active_trades['symbol'] == symbol]
    assert len(trade_row) == 1
    assert trade_row.iloc[0]['side'] == "LONG"
    assert float(trade_row.iloc[0]['open_price']) == 3500.0
    assert float(trade_row.iloc[0]['quantity']) == 1.5

    # 2. Test log trade close
    await db_manager.log_trade_close(symbol, 3600.0, 2.85, 150.0)

    # Verify no open trades remain
    active_trades_after = await db_manager.get_active_trades()
    assert active_trades_after[active_trades_after['symbol'] == symbol].empty

    # Verify trade is archived in trade history
    history = await db_manager.get_trade_history()
    assert not history.empty
    archived_row = history[history['symbol'] == symbol]
    assert len(archived_row) == 1
    assert archived_row.iloc[0]['status'] == "CLOSED"
    assert float(archived_row.iloc[0]['close_price']) == 3600.0
    assert float(archived_row.iloc[0]['pnl_usdt']) == 150.0
