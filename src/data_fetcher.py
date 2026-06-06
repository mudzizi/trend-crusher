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

    def save_ohlcv(self, symbol, timeframe, days=365):
        os.makedirs(self.c.get("DATA_DIR", "data"), exist_ok=True)
        clean_sym = symbol.replace('/', '_').replace(':', '_')
        filename = f"{self.c.get('DATA_DIR', 'data')}/{clean_sym}_{timeframe}.csv"
        
        existing_df = pd.DataFrame()
        if os.path.exists(filename):
            try:
                existing_df = pd.read_csv(filename)
                if not existing_df.empty:
                    last_ts = pd.to_datetime(existing_df['timestamp'].iloc[-1])
                    since_ms = int(last_ts.timestamp() * 1000) + 1
                    if (datetime.now() - last_ts).total_seconds() < 300:
                        return # Up to date
                else:
                    since_ms = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
            except:
                since_ms = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
        else:
            since_ms = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())

        new_df = self.fetch_ohlcv(symbol, timeframe, since_ms)
        if not new_df.empty:
            if not existing_df.empty:
                existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'])
                combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=['timestamp']).reset_index(drop=True)
            else:
                combined_df = new_df
            combined_df.to_csv(filename, index=False)
            print(f"Updated {filename}: Added {len(new_df)} new rows.")

    def save_all(self, symbol=None, days=None):
        symbol = symbol if symbol else self.c.get("SYMBOL", "BTC/USDT")
        days = days if days else self.c.get("BACKTEST_DAYS", 365)
        
        timeframes = []
        for key in ["SIGNAL_TIMEFRAME", "TREND_TIMEFRAME", "CHECK_TIMEFRAME"]:
            if key in self.c: timeframes.append(self.c[key])
        
        if not timeframes: timeframes = ["1h", "4h", "1m"]
        
        for tf in list(set(timeframes)):
            self.save_ohlcv(symbol, tf, days)

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    top_symbols = fetcher.get_top_symbols()
    print(f"Top Symbols: {top_symbols}")
    # fetcher.save_all()
