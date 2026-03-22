import pytest
import asyncio
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch
from scripts.live_bot_async import SymbolBotAsync
from src.indicators import calculate_donchian, calculate_atr, calculate_adx, calculate_ema

@pytest.fixture
def mock_dependencies():
    mock_exchange = AsyncMock()
    mock_pm = AsyncMock()
    mock_notifier = AsyncMock()
    mock_db = MagicMock()
    
    # Setup mock PM to return valid quantities
    mock_pm.calculate_order_qty = AsyncMock(return_value=1.0)
    mock_pm.get_symbol_equity = AsyncMock(return_value=1000.0)
    
    return mock_exchange, mock_pm, mock_notifier, mock_db

def generate_historical_data(symbol, end_ts, count=100):
    """Generate 100 hours of upward trending data."""
    data = []
    base_price = 50000.0
    for i in range(count):
        ts = end_ts - pd.Timedelta(hours=count-i)
        price = base_price + (i * 10) # Slow uptrend
        data.append([
            int(ts.timestamp() * 1000), 
            price, price + 50, price - 50, price + 10, 1000.0
        ])
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

@pytest.mark.asyncio
async def test_e2e_trading_cycle_simulation(mock_dependencies):
    """
    Simulates a full trading cycle:
    1. Startup & Initialization
    2. Price Breakout (Entry Trigger)
    3. Price Growth (Trailing Stop Adjustment)
    4. Price Reversal (Exit Trigger)
    """
    mock_exchange, mock_pm, mock_notifier, mock_db = mock_dependencies
    symbol = "BTC/USDT"
    
    # 1. Setup Bot
    bot = SymbolBotAsync(symbol, mock_exchange, mock_pm, mock_notifier, mock_db)
    bot.settings.update({
        "DRY_RUN": True,
        "VOL_MULTIPLIER": 0.0, # Disable vol filter
        "ADX_FILTER_LEVEL": -1, # Disable ADX filter
        "EMA_TREND_PERIOD": 20, # Use shorter EMA for faster sync
        "DONCHIAN_PERIOD": 10,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "1h", # Same for simplicity
        "USE_SNIPER": False,
        "USE_RETEST_MAKER": False,
        "INITIAL_SL_ATR": 2.0,
        "TRAILING_ATR_MULT": 3.0
    })
    
    # Generate data with a clear EMA trend (price > EMA)
    now = pd.Timestamp.now().floor('h')
    hist_df = generate_historical_data(symbol, now, count=100)
    bot.ohlcv_1h = hist_df.copy()
    bot.ohlcv_4h = hist_df.copy()
    
    async def mock_fetch_ohlcv(tf, limit=100):
        df = hist_df if tf == "1h" else hist_df
        data = []
        for _, row in df.iterrows():
            data.append([int(row['timestamp'].timestamp()*1000), row['open'], row['high'], row['low'], row['close'], row['volume']])
        return data

    mock_exchange.fetch_ohlcv = AsyncMock(side_effect=mock_fetch_ohlcv)
    
    # 2. Simulate Price Breakout (Taker Entry)
    upper, _ = calculate_donchian(bot.ohlcv_1h, bot.settings["DONCHIAN_PERIOD"])
    breakout_price = upper.iloc[-1] + 1000.0
    
    last_ts = bot.ohlcv_1h.iloc[-1]['timestamp']
    kline_msg = {
        't': int(last_ts.timestamp() * 1000),
        'o': str(breakout_price - 100),
        'h': str(breakout_price + 200),
        'l': str(breakout_price - 200),
        'c': str(breakout_price),
        'v': '10000',
        'x': False,
        'i': '1h'
    }
    
    assert bot.position == 0
    await bot.on_kline_update("1h", kline_msg)
    
    # DEBUG: print states if failed
    if bot.position != 1:
        print(f"\nDEBUG: last_price={bot.last_price}")
        df_1h, df_4h = bot.ohlcv_1h, bot.ohlcv_4h
        upper, lower = calculate_donchian(df_1h, bot.settings["DONCHIAN_PERIOD"])
        ema_4h = calculate_ema(df_4h, bot.settings["EMA_TREND_PERIOD"]).iloc[-1]
        print(f"DEBUG: top_level={upper.iloc[-1]}, bottom_level={lower.iloc[-1]}, ema_4h={ema_4h}")

    assert bot.position == 1
    assert bot.entry_price == breakout_price
    mock_db.log_trade_open.assert_called()
    
    # 3. Simulate Price Growth
    growth_price = breakout_price + 3000.0
    await bot.on_mark_price_update(growth_price)
    assert bot.max_price_seen == growth_price
    
    # 4. Simulate Price Reversal
    crash_price = growth_price - 6000.0 # Deep crash
    await bot.on_mark_price_update(crash_price)
    
    assert bot.position == 0
    mock_db.log_trade_close.assert_called()
    
    print(f"\n✅ E2E Simulation Success: Entry at {breakout_price}, Exit at {crash_price}")

@pytest.mark.asyncio
async def test_e2e_concurrency_isolation(mock_dependencies):
    """
    Verifies that multiple bots don't interfere with each other's capital/state.
    """
    mock_exchange, mock_pm, mock_notifier, mock_db = mock_dependencies
    
    bot_btc = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    bot_eth = SymbolBotAsync("ETH/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    
    # Disable filters to ensure entry
    for b in [bot_btc, bot_eth]:
        b.settings.update({
            "VOL_MULTIPLIER": 0.0,
            "ADX_FILTER_LEVEL": -1,
            "EMA_TREND_PERIOD": 50,
            "DONCHIAN_PERIOD": 20,
            "DRY_RUN": True
        })
    
    now = pd.Timestamp.now().floor('h')
    hist_btc = generate_historical_data("BTC/USDT", now)
    hist_eth = generate_historical_data("ETH/USDT", now)
    
    bot_btc.ohlcv_1h = hist_btc.copy()
    bot_btc.ohlcv_4h = hist_btc.copy()
    bot_eth.ohlcv_1h = hist_eth.copy()
    bot_eth.ohlcv_4h = hist_eth.copy()
    
    # Trigger BTC entry
    bot_btc.last_price = 100000.0 
    await bot_btc.check_entry()
    
    assert bot_btc.position != 0
    assert bot_eth.position == 0 
    
    print("✅ E2E Concurrency Isolation Verified.")

if __name__ == "__main__":
    pytest.main([__file__])
