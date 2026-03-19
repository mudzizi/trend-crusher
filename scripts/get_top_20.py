import ccxt
import pandas as pd

def get_top_20_usdt_m():
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    print("Fetching tickers...")
    tickers = exchange.fetch_tickers()
    print(f"Total tickers: {len(tickers)}")
    
    # USDT-M pairs only
    usdt_m_tickers = {symbol: data for symbol, data in tickers.items() if '/USDT' in symbol}
    print(f"USDT-M tickers: {len(usdt_m_tickers)}")
    
    # Sort by 24h quote volume
    sorted_tickers = sorted(usdt_m_tickers.items(), key=lambda x: x[1]['quoteVolume'] if 'quoteVolume' in x[1] else 0, reverse=True)
    
    top_20 = sorted_tickers[:20]
    
    print(f"{'Symbol':<15} | {'24h Volume (USDT)':<20}")
    print("-" * 40)
    symbols = []
    for symbol, data in top_20:
        print(f"{symbol:<15} | {data['quoteVolume']:<20.2f}")
        symbols.append(symbol)
    return symbols

if __name__ == "__main__":
    get_top_20_usdt_m()
