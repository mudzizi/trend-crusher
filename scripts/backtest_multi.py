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

def run_backtest(symbol, params):
    # 설정 업데이트
    test_config = CONFIG.copy()
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
    print(f"Params: Vol_Mult={params['VOL_MULTIPLIER']}, Trail={params['TRAILING_ATR_MULT']}, Risk={params['RISK_PER_TRADE']}, EMA={params['EMA_TREND_PERIOD']}")
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
    targets = [
        {
            "symbol": "TRUMP/USDT",
            "params": {"VOL_MULTIPLIER": 2.5, "TRAILING_ATR_MULT": 4.5, "RISK_PER_TRADE": 0.02, "EMA_TREND_PERIOD": 100}
        },
        {
            "symbol": "ETH/USDT",
            "params": {"VOL_MULTIPLIER": 2.0, "TRAILING_ATR_MULT": 4.5, "RISK_PER_TRADE": 0.02, "EMA_TREND_PERIOD": 200}
        },
        {
            "symbol": "XAU/USDT", 
            "params": {"VOL_MULTIPLIER": 2.5, "TRAILING_ATR_MULT": 4.5, "RISK_PER_TRADE": 0.02, "EMA_TREND_PERIOD": 200}
        }
    ]
    
    summary = []
    for target in targets:
        res = run_backtest(target['symbol'], target['params'])
        if res:
            summary.append(res)
            
    print("\n" + "="*50)
    print(" BACKTEST SUMMARY (ADX + PARTIAL TP) ")
    print("="*50)
    for s in summary:
        print(f"{s['symbol']:<12} | Return: {s['return']:>8.2f}% | MDD: {s['mdd']:>6.2f}% | Trades: {s['trades']}")
    print("="*50)
