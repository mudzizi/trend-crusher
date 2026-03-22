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

    def get_top_symbols(self, limit=20):
        print(f"Fetching top {limit} symbols by volume...")
        try:
            tickers = self.exchange.fetch_tickers()
            # USDT-M Futures only (e.g., 'BTC/USDT:USDT')
            usdt_tickers = []
            for symbol, ticker in tickers.items():
                if '/USDT:USDT' in symbol:
                    # Filter out leveraged tokens or unusual non-alphabet symbols
                    clean_sym = symbol.split(':')[0]
                    if any(c.isalpha() for c in clean_sym):
                        usdt_tickers.append({
                            'symbol': clean_sym,
                            'volume': float(ticker.get('quoteVolume', 0))
                        })
            
            sorted_tickers = sorted(usdt_tickers, key=lambda x: x['volume'], reverse=True)[:limit]
            return [t['symbol'] for t in sorted_tickers]
        except Exception as e:
            print(f"Error fetching top symbols: {e}")
            return []

    def save_all(self, symbol=None, days=None):
        os.makedirs(self.c["DATA_DIR"], exist_ok=True)
        symbol = symbol if symbol else self.c["SYMBOL"]
        days = days if days else self.c["BACKTEST_DAYS"]
        
        # Clean symbol name for filename
        clean_sym = symbol.replace('/', '_').replace(':', '_')
        
        for tf in [self.c["SIGNAL_TIMEFRAME"], self.c["TREND_TIMEFRAME"], self.c["CHECK_TIMEFRAME"]]:
            filename = f"{self.c['DATA_DIR']}/{clean_sym}_{tf}.csv"
            
            # Skip if recently updated (within 1 hour)
            if os.path.exists(filename):
                mtime = os.path.getmtime(filename)
                if time.time() - mtime < 3600:
                    print(f"Data for {symbol} {tf} is up to date. Skipping...")
                    continue

            df = self.fetch_ohlcv(symbol, tf, days)
            df.to_csv(filename, index=False)
            print(f"Saved to {filename}")

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    top_symbols = fetcher.get_top_symbols()
    print(f"Top Symbols: {top_symbols}")
    # fetcher.save_all()
