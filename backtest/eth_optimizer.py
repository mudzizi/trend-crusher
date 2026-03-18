import pandas as pd
import numpy as np
from src.strategy import AggressiveVBOStrategy

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_eth_optimization():
    df_1h = pd.read_csv("data/ETH_USDT_1h.csv")
    df_4h = pd.read_csv("data/ETH_USDT_4h.csv")
    
    risks = [0.01, 0.015, 0.02]
    results = []
    
    for r in risks:
        strategy = AggressiveVBOStrategy()
        trades, equity_curve = strategy.run(df_1h, df_4h, risk_pct=r)
        
        final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        total_trades = len([t for t in trades if t['type'] == 'CLOSE'])
        
        # Risk-Adjusted Return (Final Return / MDD)
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
    print("\n[ETH Aggressive VBO] Risk Optimization Results (1-Year):")
    print(summary.to_string(index=False))
