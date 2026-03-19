import ccxt
import pandas as pd
import os
import sys
import time

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

def get_top_20_volumes():
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    tickers = exchange.fetch_tickers()
    
    # USDT 페어만 필터링 (심볼 형식: 'ETH/USDT:USDT')
    usdt_tickers = []
    for symbol, ticker in tickers.items():
        if '/USDT:USDT' in symbol:
            usdt_tickers.append({
                'symbol': symbol.split(':')[0], # 'ETH/USDT' 형태로 추출
                'volume': float(ticker.get('quoteVolume', 0))
            })
    
    # 거래대금 내림차순 정렬 후 상위 20개 추출
    top_20 = sorted(usdt_tickers, key=lambda x: x['volume'], reverse=True)[:20]
    return [t['symbol'] for t in top_20]

def collect_mega_data():
    symbols = get_top_20_volumes()
    print(f"🚀 Top 20 Symbols by Volume: {symbols}")
    
    fetcher = BinanceDataFetcher()
    # 365일 전체 데이터 수집 설정
    fetcher.c["BACKTEST_DAYS"] = 365
    
    for symbol in symbols:
        print(f"\n--- Processing {symbol} (Fetching 365 days) ---")
        fetcher.c["SYMBOL"] = symbol
        try:
            fetcher.save_all()
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
        time.sleep(1) # rate limit 방지

if __name__ == "__main__":
    collect_mega_data()
