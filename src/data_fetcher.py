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

    def fetch_ohlcv(self, symbol, timeframe, since_days):
        print(f"Fetching {timeframe} data for {symbol} (last {since_days} days)...")
        since = self.exchange.parse8601((datetime.now() - timedelta(days=since_days)).isoformat())
        all_ohlcv = []
        
        while since < self.exchange.milliseconds():
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since)
                if not ohlcv: break
                since = ohlcv[-1][0] + 1
                all_ohlcv += ohlcv
                time.sleep(self.exchange.rateLimit / 1000)
            except Exception as e:
                print(f"Error: {e}"); time.sleep(10)
        
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def save_all(self):
        os.makedirs(self.c["DATA_DIR"], exist_ok=True)
        symbol = self.c["SYMBOL"]
        days = self.c["BACKTEST_DAYS"]
        
        for tf in [self.c["SIGNAL_TIMEFRAME"], self.c["TREND_TIMEFRAME"], self.c["CHECK_TIMEFRAME"]]:
            df = self.fetch_ohlcv(symbol, tf, days)
            filename = f"{self.c['DATA_DIR']}/{symbol.replace('/', '_')}_{tf}.csv"
            df.to_csv(filename, index=False)
            print(f"Saved to {filename}")

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    fetcher.save_all()
