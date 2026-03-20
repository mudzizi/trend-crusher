import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.visualizer import TradingVisualizer
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_backtest(symbol, params=None):
    # 1. Base config
    test_config = CONFIG.copy()
    
    # 2. Override with Symbol Specific Settings from config.py
    if "SYMBOL_SETTINGS" in CONFIG and symbol in CONFIG["SYMBOL_SETTINGS"]:
        test_config.update(CONFIG["SYMBOL_SETTINGS"][symbol])
        
    # 3. Override with manually passed params (if any)
    if params:
        test_config.update(params)
        
    test_config["SYMBOL"] = symbol
    
    # 데이터 경로 확인 및 다운로드
    clean_sym = symbol.replace('/', '_')
    f_sig = f"data/{clean_sym}_1h.csv"
    f_trend = f"data/{clean_sym}_4h.csv"
    f_check = f"data/{clean_sym}_1m.csv"
    
    if not all(os.path.exists(f) for f in [f_sig, f_trend, f_check]):
        print(f"Downloading data for {symbol}...")
        fetcher = BinanceDataFetcher(config=test_config)
        fetcher.save_all()
    
    print(f">>> Running Backtest for {symbol} <<<")
    print(f"Params: Vol_Mult={test_config['VOL_MULTIPLIER']}, Trail={test_config['TRAILING_ATR_MULT']}, Risk={test_config['RISK_PER_TRADE']}, EMA={test_config['EMA_TREND_PERIOD']}")
    print(f"New Features: ADX_Filter={test_config['ADX_FILTER_LEVEL']}, Adaptive_Trail={test_config.get('USE_ADAPTIVE_TRAIL', False)}")

    df_sig = pd.read_csv(f_sig)
    df_trend = pd.read_csv(f_trend)
    df_check = pd.read_csv(f_check)
    
    strategy = TrendCrusherV2(config=test_config)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)
    
    if not trades:
        print(f"No trades executed for {symbol}.")
        return None

    # 결과 분석
    processed_trades = []
    for i in range(0, len(trades), 2):
        if i+1 < len(trades):
            o, c = trades[i], trades[i+1]
            processed_trades.append({
                'open_time': o['time'],
                'close_time': c['time'],
                'side': o['side'],
                'open_price': o['price'],
                'close_price': c['price'],
                'pnl_usdt': c['pnl_usdt']
            })

    trades_df = pd.DataFrame(processed_trades)
    
    # Equity history (Visualizer용)
    equity_df = pd.DataFrame([
        {'timestamp': df_sig.iloc[i]['timestamp'] if i < len(df_sig) else df_sig.iloc[-1]['timestamp'], 'balance': val}
        for i, val in enumerate(equity_curve)
    ])
    
    # 최종 성과
    final_cap = strategy.capital
    ret = ((final_cap / test_config["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    
    print("-" * 30)
    print(f"Return: {ret:+.2f}%")
    print(f"MDD: {mdd:.2f}%")
    print(f"Trades: {len(processed_trades)}")
    print("-" * 30)
    
    return {
        'symbol': symbol,
        'return': ret,
        'mdd': mdd,
        'trades': len(processed_trades)
    }

if __name__ == "__main__":
    targets = CONFIG.get("SYMBOLS_LIST", ["TRUMP/USDT", "ETH/USDT", "XAU/USDT"])
    
    summary = []
    for symbol in targets:
        # run_backtest now automatically loads SYMBOL_SETTINGS from config.py
        res = run_backtest(symbol)
        if res:
            summary.append(res)
            
    print("\n" + "="*50)
    print(" FINAL S-TIER BACKTEST SUMMARY ")
    print("="*50)
    for s in summary:
        print(f"{s['symbol']:<12} | Return: {s['return']:>8.2f}% | MDD: {s['mdd']:>6.2f}% | Trades: {s['trades']}")
    print("="*50)
