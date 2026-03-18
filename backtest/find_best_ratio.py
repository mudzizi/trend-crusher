import pandas as pd
import numpy as np
import os
from src.strategy import SupertrendMacdRsiStrategy

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def optimize():
    timeframes = ['15m', '30m', '1h', '4h']
    ratios = np.arange(0.5, 1.0, 0.05)
    
    df_4h = pd.read_csv("data/BTC_USDT_4h.csv")
    
    all_results = []
    
    for tf in timeframes:
        filepath = f"data/BTC_USDT_{tf}.csv"
        if not os.path.exists(filepath):
            continue
        
        df = pd.read_csv(filepath)
        print(f"Optimizing {tf}...")
        
        best_return = -float('inf')
        best_ratio = 0
        
        for ratio in ratios:
            strategy = SupertrendMacdRsiStrategy()
            
            if tf in ['15m', '30m', '1h']:
                trades, equity_curve = strategy.run(df, df_4h, trailing_ratio=ratio)
            else:
                trades, equity_curve = strategy.run(df, trailing_ratio=ratio)
            
            final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
            mdd = calculate_mdd(equity_curve) * 100
            total_trades = len([t for t in trades if t['type'] == 'CLOSE'])
            
            all_results.append({
                'Timeframe': tf,
                'Ratio': round(ratio, 2),
                'Return (%)': round(final_return, 2),
                'MDD (%)': round(mdd, 2),
                'Trades': total_trades
            })
            
    return pd.DataFrame(all_results)

if __name__ == "__main__":
    results_df = optimize()
    
    print("\n[Optimization Results Summary]")
    # Find best ratio per timeframe
    best_per_tf = results_df.loc[results_df.groupby('Timeframe')['Return (%)'].idxmax()]
    print(best_per_tf.to_string(index=False))
    
    # Save all results to CSV for analysis
    results_df.to_csv("optimization_results.csv", index=False)
    print("\nFull results saved to optimization_results.csv")
