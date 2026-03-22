import ccxt
import pandas as pd
import time
import os
from datetime import datetime, timedelta
from src.config import CONFIG

class BinanceDataFetcher:
    def __init__(self, config=CONFIG):
        self.c = config
        self.exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'enableRateLimit': True
        })

    def fetch_ohlcv(self, symbol, timeframe, since_ms):
        """
        Fetch OHLCV data starting from a specific millisecond timestamp.
        """
        since_str = datetime.fromtimestamp(since_ms/1000).strftime('%Y-%m-%d %H:%M')
        print(f"Fetching {timeframe} data for {symbol} starting from {since_str}...")
        
        all_ohlcv = []
        while since_ms < self.exchange.milliseconds():
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since_ms)
                if not ohlcv: break
                since_ms = ohlcv[-1][0] + 1
                all_ohlcv += ohlcv
                # Prevent aggressive polling
                time.sleep(self.exchange.rateLimit / 1000)
            except Exception as e:
                print(f"Error fetching {symbol} {timeframe}: {e}")
                time.sleep(10)
        
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def save_all(self, symbol=None, days=None):
        os.makedirs(self.c["DATA_DIR"], exist_ok=True)
        symbol = symbol if symbol else self.c["SYMBOL"]
        days = days if days else self.c.get("BACKTEST_DAYS", 365)
        
        clean_sym = symbol.replace('/', '_').replace(':', '_')
        
        for tf in [self.c["SIGNAL_TIMEFRAME"], self.c["TREND_TIMEFRAME"], self.c["CHECK_TIMEFRAME"]]:
            filename = f"{self.c['DATA_DIR']}/{clean_sym}_{tf}.csv"
            existing_df = pd.DataFrame()
            
            # 1. Determine the 'since' point
            if os.path.exists(filename):
                try:
                    existing_df = pd.read_csv(filename)
                    if not existing_df.empty:
                        last_ts = pd.to_datetime(existing_df['timestamp'].iloc[-1])
                        # Last timestamp + 1ms to avoid duplication
                        since_ms = int(last_ts.timestamp() * 1000) + 1
                        
                        # Optimization: if file is very recent (within 5m), skip
                        if (datetime.now() - last_ts).total_seconds() < 300:
                            print(f"Data for {symbol} {tf} is up to date. Skipping...")
                            continue
                    else:
                        since_ms = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
                except Exception as e:
                    print(f"Error reading existing file {filename}: {e}")
                    since_ms = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
            else:
                since_ms = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())

            # 2. Fetch only the new data
            new_df = self.fetch_ohlcv(symbol, tf, since_ms)
            
            # 3. Combine and Save
            if not new_df.empty:
                if not existing_df.empty:
                    # Convert existing timestamp to datetime for clean concatenation
                    existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'])
                    combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=['timestamp']).reset_index(drop=True)
                else:
                    combined_df = new_df
                
                combined_df.to_csv(filename, index=False)
                print(f"Updated {filename}: Added {len(new_df)} new rows.")
            else:
                print(f"No new data found for {symbol} {tf}.")

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    top_symbols = fetcher.get_top_symbols()
    print(f"Top Symbols: {top_symbols}")
    # fetcher.save_all()
