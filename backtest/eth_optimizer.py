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

def run_eth_optimization():
    symbol = "ETH/USDT"
    clean_sym = symbol.replace('/', '_')
    f1h, f4h, f1m = f"data/{clean_sym}_1h.csv", f"data/{clean_sym}_4h.csv", f"data/{clean_sym}_1m.csv"
    
    if not all(os.path.exists(f) for f in [f1h, f4h, f1m]):
        print(f"Skipping {symbol}: Files not found (requires 1h, 4h, and 1m).")
        return pd.DataFrame()

    df_1h = pd.read_csv(f1h)
    df_4h = pd.read_csv(f4h)
    df_1m = pd.read_csv(f1m)
    
    risks = [0.01, 0.015, 0.02]
    results = []
    
    for r in risks:
        strategy = TrendCrusherV2()
        trades, equity_curve = strategy.run_precision_backtest(df_1h, df_4h, df_1m, risk_pct=r)
        
        final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        total_trades = len([t for t in trades if t['type'] == 'CLOSE'])
        
        rar = final_return / mdd if mdd > 0 else 0
        
        results.append({
            'Risk Per Trade (%)': r * 100,
            'Total Trades': total_trades,
            'Final Return (%)': round(final_return, 2),
            'MDD (%)': round(mdd, 2),
            'Return/MDD Ratio': round(rar, 2)
        })
        
    return pd.DataFrame(results)

if __name__ == "__main__":
    summary = run_eth_optimization()
    if not summary.empty:
        print("\n[ETH Aggressive VBO] Risk Optimization Results (1-Year):")
        print(summary.to_string(index=False))
