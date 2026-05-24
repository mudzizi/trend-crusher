import pandas as pd
import numpy as np
import os
from src.strategy import TrendCrusherV2

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_precision_backtest():
    # 1. 데이터 로드 (신호용 1h, 검증용 1m)
    symbol = "ETH/USDT"
    clean_sym = symbol.replace('/', '_')
    f1h, f4h, f1m = f"data/{clean_sym}_1h.csv", f"data/{clean_sym}_4h.csv", f"data/{clean_sym}_1m.csv"
    
    if not all(os.path.exists(f) for f in [f1h, f4h, f1m]):
        print(f"Skipping {symbol}: Files not found.")
        return

    df_1h = pd.read_csv(f1h)
    df_4h = pd.read_csv(f4h)
    df_1m = pd.read_csv(f1m)
    
    # 전략 초기화
    strategy = TrendCrusherV2()
    
    print(f"Starting Precision Backtest for {symbol} (Using Refactored Engine)...")
    
    trades, equity_curve = strategy.run_precision_backtest(df_1h, df_4h, df_1m)

    # 결과 리포트
    final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    print(f"\n[Precision Results]")
    print(f"Final Return: {final_return:.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Total Trades: {len([t for t in trades if t['type']=='CLOSE'])}")

if __name__ == "__main__":
    run_precision_backtest()
