import ccxt
import pandas as pd
import time
import os
from datetime import datetime, timezone
from src.config import CONFIG

# --- CONFIGURATION ---
SYMBOLS = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "TRUMP/USDT"]
START_DATE = "2024-01-01 00:00:00"
END_DATE = "2024-12-31 23:59:00"
TIMEFRAME = "1m"
DATA_DIR = "data"
# ---------------------

def fetch_period_data(exchange, symbol, timeframe, start_ms, end_ms):
    clean_sym = symbol.replace('/', '_').replace(':', '_')
    filename = f"{DATA_DIR}/{clean_sym}_2024_{timeframe}.csv"
    
    print(f"\n🚀 Fetching {symbol} for 2024...")
    
    all_ohlcv = []
    current_ms = start_ms
    
    # Binance fetch_ohlcv limit is usually 1000 candles
    # 1 year 1m = 525,600 candles. 
    
    while current_ms < end_ms:
        try:
            # Check for current time to avoid fetching future
            if current_ms > exchange.milliseconds():
                break
                
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, current_ms, limit=1000)
            if not ohlcv:
                print(f"   - No more data for {symbol}")
                break
            
            last_ts = ohlcv[-1][0]
            # Filter data strictly within 2024
            valid_data = [c for t in ohlcv if (c := t) and t[0] <= end_ms]
            all_ohlcv += valid_data
            
            # Progress log
            dt_str = datetime.fromtimestamp(last_ts/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
            print(f"   - Progress: {dt_str} | Total: {len(all_ohlcv)} rows", end='\r')
            
            if last_ts >= end_ms:
                break
                
            current_ms = last_ts + 60000 # Next minute
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            print(f"\n   - Error: {e}")
            time.sleep(10)
            
    if all_ohlcv:
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.to_csv(filename, index=False)
        print(f"\n✅ Saved {len(df)} rows to {filename}")
    else:
        print(f"\n⚠️ No data found for {symbol} in 2024.")

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    exchange = ccxt.binance({
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    
    start_ms = exchange.parse8601(START_DATE.replace(' ', 'T') + 'Z')
    end_ms = exchange.parse8601(END_DATE.replace(' ', 'T') + 'Z')
    
    for sym in SYMBOLS:
        fetch_period_data(exchange, sym, TIMEFRAME, start_ms, end_ms)

if __name__ == "__main__":
    main()
