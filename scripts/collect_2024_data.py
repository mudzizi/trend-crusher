import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timedelta

def fetch_historical_window(symbol, timeframe, start_date_str, end_date_str):
    exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
    since_ms = exchange.parse8601(f"{start_date_str}T00:00:00Z")
    end_ms = exchange.parse8601(f"{end_date_str}T00:00:00Z")
    
    clean_sym = symbol.replace('/', '_')
    filename = f"data/{clean_sym}_{timeframe}_hist_2024.csv"
    
    if os.path.exists(filename):
        print(f"File {filename} already exists. Loading...")
        return pd.read_csv(filename, parse_dates=['timestamp'])

    print(f"🚀 Fetching {timeframe} data for {symbol} from {start_date_str} to {end_date_str}...")
    
    all_ohlcv = []
    current_since = since_ms
    
    while current_since < end_ms:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, current_since, limit=1000)
            if not ohlcv: break
            
            # Filter only up to end_ms
            filtered = [row for row in ohlcv if row[0] < end_ms]
            if not filtered: break
            
            all_ohlcv += filtered
            current_since = ohlcv[-1][0] + 1
            
            print(f"Progress: {datetime.fromtimestamp(current_since/1000).strftime('%Y-%m-%d %H:%M')} | Total: {len(all_ohlcv)}")
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.to_csv(filename, index=False)
    print(f"✅ Saved to {filename}")
    return df

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    # Fetch 1h data (fast)
    symbols = ["ETH/USDT", "SOL/USDT", "XRP/USDT", "TRUMP/USDT"]
    for sym in symbols:
        fetch_historical_window(sym, "1h", "2024-05-10", "2025-05-10")
