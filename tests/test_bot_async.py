import pytest
import asyncio
import pandas as pd
import numpy as np
import time
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.live_bot_async import SymbolBotAsync
from src.config import CONFIG
from src.async_db_manager import AsyncDBManager as DBManager
from src.portfolio_manager_async import PortfolioManagerAsync
from src.telegram_utils import TelegramNotifier
from src.websocket_manager import BinanceWebSocketManager
from src.strategy import TrendCrusherV2

@pytest.fixture
def mock_bot():
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_pm.calculate_order_qty = AsyncMock(return_value=1.0)
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    settings = CONFIG.copy()
    settings.update({
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "DONCHIAN_PERIOD": 20,
        "ATR_PERIOD": 14,
        "AVG_VOL_PERIOD": 20,
        "VOL_MULTIPLIER": 1.5,
        "ADX_FILTER_LEVEL": 25,
        "EMA_TREND_PERIOD": 200,
        "DRY_RUN": True,
        "INITIAL_SL_ATR": 2.0
    })
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings = settings
    
    # Initialize mock OHLCV buffers
    now = pd.Timestamp.now().floor('h')
    data = []
    for i in range(100):
        data.append([now - pd.Timedelta(hours=100-i), 50000.0, 51000.0, 49000.0, 50500.0, 1000.0])
    
    bot.ohlcv_1h = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    bot.ohlcv_4h = bot.ohlcv_1h.copy()
    bot.df_indicators = pd.DataFrame([{'upper': 1000, 'lower': 900, 'ema_h': 950, 'atr': 20, 'volume': 1000, 'adx': 25, 'avg_vol': 500}])
    bot.last_price = 50000.0
    
    return bot

# --- From test_async_realtime.py ---
@pytest.mark.asyncio
async def test_on_kline_update_realtime_modification(mock_bot):
    last_ts = mock_bot.ohlcv_1h.iloc[-1]['timestamp']
    kline_msg = {
        't': int(last_ts.timestamp() * 1000),
        'o': '50500',
        'h': '52000',
        'l': '50000',
        'c': '51500',
        'v': '1500',
        'x': False
    }
    mock_bot.check_entry = AsyncMock()
    mock_bot.check_exit = AsyncMock()
    
    await mock_bot.on_kline_update("1h", kline_msg)
    assert len(mock_bot.ohlcv_1h) == 100
    updated_row = mock_bot.ohlcv_1h.iloc[-1]
    assert updated_row['high'] == 52000.0
    assert updated_row['close'] == 51500.0
    assert updated_row['volume'] == 1500.0

@pytest.mark.asyncio
async def test_on_kline_update_new_candle_sync(mock_bot):
    last_ts = mock_bot.ohlcv_1h.iloc[-1]['timestamp']
    new_ts = last_ts + pd.Timedelta(hours=1)
    kline_msg = {
        't': int(new_ts.timestamp() * 1000),
        'o': '51500', 'h': '51600', 'l': '51400', 'c': '51550', 'v': '100', 'x': True
    }
    mock_bot.fetch_ohlcv = AsyncMock(return_value=mock_bot.ohlcv_1h)
    await mock_bot.on_kline_update("1h", kline_msg)
    mock_bot.fetch_ohlcv.assert_called_with("1h", limit=1000)

@pytest.mark.asyncio
async def test_on_kline_update_logs_correct_closed_candle(mock_bot):
    ts_closed = pd.Timestamp.now().floor('h') - pd.Timedelta(hours=1)
    ts_new = pd.Timestamp.now().floor('h')
    
    mock_bot.df_indicators = pd.DataFrame([
        {
            'close': 1.18, 'ema_h': 1.17, 'upper': 1.20, 'lower': 1.10,
            'volume': 9000000.0, 'adx': 25.0, 'chaos': 20.0, 'squeeze': 0.0,
            'ema_slope': 0.001, 'chop': 35.0, 'adx_4h': 22.0
        },
        {
            'close': 1.23, 'ema_h': 1.18, 'upper': 1.25, 'lower': 1.12,
            'volume': 150.0, 'adx': 26.0, 'chaos': 21.0, 'squeeze': 0.0,
            'ema_slope': 0.002, 'chop': 36.0, 'adx_4h': 23.0
        }
    ], index=[ts_closed, ts_new])
    
    mock_bot.fetch_ohlcv = AsyncMock(return_value=mock_bot.ohlcv_1h)
    mock_bot.db.log_history_1h = AsyncMock()
    
    kline_msg = {
        't': int(ts_closed.timestamp() * 1000),
        'o': '1.18', 'h': '1.20', 'l': '1.10', 'c': '1.18', 'v': '9000000', 'x': True
    }
    
    await mock_bot.on_kline_update("1h", kline_msg)
    
    mock_bot.db.log_history_1h.assert_called_once()
    called_args = mock_bot.db.log_history_1h.call_args[0]
    assert called_args[6] == 9000000.0

@pytest.mark.asyncio
async def test_on_kline_update_ignore_irrelevant_tf(mock_bot):
    mock_bot.fetch_ohlcv = AsyncMock()
    mock_bot.check_entry = AsyncMock()
    kline_msg = {
        't': 1600000000000, 'o': '1', 'h': '1', 'l': '1', 'c': '1', 'v': '1', 'x': True, 'i': '1m'
    }
    await mock_bot.on_kline_update("1m", kline_msg)
    mock_bot.fetch_ohlcv.assert_not_called()
    mock_bot.check_entry.assert_not_called()

@pytest.mark.asyncio
async def test_retest_order_placement_state(mock_bot):
    target_price = 55000.0
    sl_price = 54000.0
    mock_bot.exchange.create_order.return_value = {'id': 'DRY_RETEST'}
    await mock_bot.manage_retest_ambush(1, target_price, sl_price)
    assert mock_bot.active_retest_order_id == "DRY_RETEST"
    assert mock_bot.sl_price == sl_price

@pytest.mark.asyncio
async def test_retest_cancel_cleanup(mock_bot):
    mock_bot.active_retest_order_id = "SOME_ID"
    mock_bot.retest_order_ts = pd.Timestamp.now()
    await mock_bot.cancel_retest_order()
    assert mock_bot.active_retest_order_id is None

# --- From test_live_bot_initialization.py ---
def test_live_bot_async_core_dependencies_defined():
    # Verify main dependencies exist and are callable/accessible
    assert SymbolBotAsync is not None
    assert DBManager is not None
    assert PortfolioManagerAsync is not None
    assert TelegramNotifier is not None
    assert BinanceWebSocketManager is not None
    assert TrendCrusherV2 is not None

def test_symbol_bot_async_instantiation_integrity():
    mock_exchange = MagicMock()
    mock_pm = MagicMock()
    mock_notifier = MagicMock()
    mock_db = MagicMock()
    
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    
    assert bot.symbol == "BTC/USDT"
    assert bot.exchange == mock_exchange
    assert bot.pm == mock_pm
    assert bot.notifier == mock_notifier
    assert bot.db == mock_db
    assert bot.position == 0
    assert bot.is_halted is False

# --- From test_live_optimizations.py ---
def test_incremental_indicator_accuracy():
    config = {
        "EMA_TREND_PERIOD": 50,
        "DONCHIAN_PERIOD": 20,
        "ATR_PERIOD": 14,
        "VOL_AVG_PERIOD": 20,
        "ADX_PERIOD": 14,
        "DRY_RUN": True,
        "INITIAL_SL_ATR": 2.0
    }
    engine = TrendCrusherV2(config)
    dates = pd.date_range(start="2023-01-01", periods=1000, freq="h")
    df_1h = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.uniform(100, 110, 1000),
        'high': np.random.uniform(110, 120, 1000),
        'low': np.random.uniform(90, 100, 1000),
        'close': np.random.uniform(100, 110, 1000),
        'volume': np.random.uniform(1000, 5000, 1000)
    })
    
    full_res = engine.calculate_indicators(df_1h, df_1h, config, is_live=False)
    full_last_row = full_res.iloc[-1]
    
    inc_res = engine.calculate_indicators(df_1h, df_1h, config, is_live=True)
    inc_last_row = inc_res.iloc[-1]
    
    assert abs(full_last_row['upper'] - inc_last_row['upper']) < 1e-4
    ema_diff_pct = abs(full_last_row['ema_h'] - inc_last_row['ema_h']) / full_last_row['ema_h']
    assert ema_diff_pct < 0.005
    assert abs(full_last_row['adx'] - inc_last_row['adx']) < 1.0

@patch('scripts.live_bot_async.DBManager')
@patch('scripts.live_bot_async.TelegramNotifier')
@pytest.mark.asyncio
async def test_throttling_logic(mock_notifier, mock_db):
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.df_indicators = pd.DataFrame([{'upper': 1000, 'lower': 900, 'ema_h': 950, 'atr': 20, 'volume': 1000, 'adx': 25, 'avg_vol': 500}])
    
    await bot.on_mark_price_update(950)
    initial_record_ts = bot.last_db_record_ts
    assert initial_record_ts != 0
    
    with patch('time.time', return_value=initial_record_ts + 1):
        await bot.on_mark_price_update(951)
        assert bot.last_db_record_ts == initial_record_ts
        
    with patch('time.time', return_value=initial_record_ts + 6):
        await bot.on_mark_price_update(952)
        assert bot.last_db_record_ts > initial_record_ts

@patch('scripts.live_bot_async.DBManager')
@patch('scripts.live_bot_async.TelegramNotifier')
@pytest.mark.asyncio
async def test_order_update_fill_logic(mock_notifier, mock_db):
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.active_sniper_order_id = "SNIPER_123"
    bot.sl_price = 9000
    
    order_msg = {
        'i': "SNIPER_123", 's': "BTCUSDT", 'X': "FILLED", 'S': "BUY", 'z': "1.0", 'L': "10000"
    }
    await bot.on_order_update(order_msg)
    assert bot.position == 1
    assert bot.entry_price == 10000
    assert bot.active_sniper_order_id is None
    assert bot.sl_order_id == "DRY_SL"

@patch('src.bot.live_bot_async.TrendCrusherV2')
@pytest.mark.asyncio
async def test_sl_sync_detection(mock_tc):
    mock_exchange = AsyncMock()
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, AsyncMock(), AsyncMock(), AsyncMock())
    bot.settings["DRY_RUN"] = False
    bot.position = 1
    bot.sl_order_id = "SL_123"
    bot.sl_price = 10000.0
    bot.last_sl_sync_price = 10000.0
    bot.last_price = 10050.0
    
    bot.engine.check_exit_signal = MagicMock(return_value=False)
    bot.sync_sl_to_exchange = AsyncMock()
    bot.df_indicators = pd.DataFrame([{'atr': 100.0}])
    
    # Case 1: Small change -> no sync
    bot.sl_price = 10001.0
    await bot.check_exit()
    bot.sync_sl_to_exchange.assert_not_called()
    
    # Case 2: Significant change -> sync
    bot.sl_price = 10005.0
    await bot.check_exit()
    bot.sync_sl_to_exchange.assert_called_once()

# --- From test_live_sync_pnl.py ---
@pytest.mark.asyncio
async def test_execute_entry_syncs_with_exchange(mock_bot):
    mock_bot.settings["DRY_RUN"] = False
    mock_bot.exchange.create_market_order.return_value = {
        'id': '123', 'symbol': 'BTC/USDT', 'side': 'buy', 'average': 50100.0, 'filled': 0.1, 'status': 'closed'
    }
    mock_bot.exchange.create_order.return_value = {'id': 'sl_123'}
    mock_bot.pm.calculate_order_qty.return_value = 0.1
    mock_bot.exchange.fetch_balance = AsyncMock(return_value={'USDT': {'free': 10000.0}})
    mock_bot.exchange.amount_to_precision = MagicMock(side_effect=lambda s, q: q)
    mock_bot.exchange.fetch_positions = AsyncMock(return_value=[{'symbol': 'BTC/USDT', 'contracts': 0}])
    
    await mock_bot.execute_entry(1, 100.0)
    assert mock_bot.entry_price == 50100.0
    assert mock_bot.quantity == 0.1
    assert mock_bot.position == 1
    mock_bot.db.log_trade_open.assert_called()

@pytest.mark.asyncio
async def test_execute_exit_calculates_real_pnl(mock_bot):
    mock_bot.settings["DRY_RUN"] = False
    mock_bot.position = 1
    mock_bot.entry_price = 50000.0
    mock_bot.quantity = 0.1
    mock_bot.last_price = 55000.0
    
    mock_bot.exchange.create_order.return_value = {
        'average': 55000.0, 'filled': 0.1, 'fee': {'cost': 2.75}
    }
    mock_bot.pm.get_total_equity.return_value = 10500.0
    
    await mock_bot.execute_exit()
    args = mock_bot.db.log_trade_close.call_args[0]
    assert args[1] == 55000.0
    assert pytest.approx(args[3], 0.1) == 497.25

@pytest.mark.asyncio
async def test_force_exit_logic(mock_bot):
    mock_bot.settings["DRY_RUN"] = False
    mock_bot.exchange.fetch_positions.return_value = [
        {'symbol': 'BTC/USDT', 'contracts': '0.05'}
    ]
    mock_bot.exchange.create_order.return_value = {
        'average': 50000.0, 'filled': 0.05, 'fee': {'cost': 1.25}
    }
    mock_bot.entry_price = 49000.0
    mock_bot.position = 1
    mock_bot.quantity = 0.05
    
    await mock_bot.force_exit()
    mock_bot.exchange.create_order.assert_any_call("BTC/USDT", "market", "sell", 0.05, None, params={'reduceOnly': True})
    assert mock_bot.position == 0
    mock_bot.db.log_trade_close.assert_called()
