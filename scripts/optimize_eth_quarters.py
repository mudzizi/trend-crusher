import pandas as pd
import numpy as np
import os
import itertools
from datetime import datetime, timedelta
from src.strategy import TrendCrusherV2
from src.config import CONFIG

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def optimize_range(df_1h, df_4h, df_1m, start_date, end_date):
    # Filter data for the specific range
    data_1h = df_1h[(df_1h['timestamp'] >= start_date) & (df_1h['timestamp'] < end_date)].copy()
    data_4h = df_4h[(df_4h['timestamp'] >= start_date) & (df_4h['timestamp'] < end_date)].copy()
    data_1m = df_1m[(df_1m['timestamp'] >= start_date) & (df_1m['timestamp'] < end_date)].copy()
    
    if len(data_1h) < 100: return None

    # Simplified Grid for speed, including adaptive trail candidates
    vol_multipliers = [1.5, 2.0, 2.5]
    trailing_mults = [3.0, 4.0]
    adx_thresholds = [15, 20, 25]
    donchian_periods = [10, 20, 30]
    # Fixed Adaptive Steps to test
    adaptive_options = [
        [], # None
        [{"pnl_pct": 2.0, "tighten_ratio": 0.5}], # Aggressive
        [{"pnl_pct": 5.0, "tighten_ratio": 0.7}]  # Moderate
    ]
    
    combinations = list(itertools.product(vol_multipliers, trailing_mults, adx_thresholds, donchian_periods, adaptive_options))
    best_eff = -1
    best_res = None
    
    for vol, trail, adx, don, adapt in combinations:
        temp_config = CONFIG.copy()
        temp_config.update({
            "SYMBOL": "ETH/USDT",
            "VOL_MULTIPLIER": vol,
            "TRAILING_ATR_MULT": trail,
            "ADX_FILTER_LEVEL": adx,
            "DONCHIAN_PERIOD": don,
            "USE_ADAPTIVE_TRAIL": len(adapt) > 0,
            "ADAPTIVE_TRAIL_STEPS": adapt,
            "RISK_PER_TRADE": 0.05 # 5% Risk
        })
        
        strategy = TrendCrusherV2(config=temp_config)
        # We use standard precision backtest for speed in optimization
        trades, equity_curve = strategy.run_precision_backtest(
            data_1h, data_4h, data_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=0.05,
            adx_threshold=adx, donchian_period=don
        )
        
        if len(trades) >= 3:
            ret = ((strategy.capital / CONFIG["SEED"]) - 1) * 100
            mdd = calculate_mdd(equity_curve) * 100
            efficiency = ret / mdd if mdd > 1.0 else (ret / 5.0) # Handle very low MDD
            
            if efficiency > best_eff:
                best_eff = efficiency
                best_res = {
                    "Return": f"{ret:.2f}%",
                    "MDD": f"{mdd:.2f}%",
                    "Eff": round(efficiency, 2),
                    "Trades": len(trades),
                    "Vol": vol,
                    "Trail": trail,
                    "ADX": adx,
                    "Donchian": don,
                    "Adaptive": "Yes" if len(adapt) > 0 else "No"
                }
    return best_res

def main():
    sym = "ETH_USDT"
    print(f"--- Quarter-by-Quarter Optimization for {sym} ---")
    
    # Load All Data
    df_1h = pd.read_csv(f"data/{sym}_1h.csv", parse_dates=['timestamp'])
    df_4h = pd.read_csv(f"data/{sym}_4h.csv", parse_dates=['timestamp'])
    df_1m = pd.read_csv(f"data/{sym}_1m.csv", parse_dates=['timestamp'])
    
    latest_date = df_1h['timestamp'].max()
    results = []
    
    for i in range(4):
        end_date = latest_date - timedelta(days=i*90)
        start_date = end_date - timedelta(days=90)
        print(f"Analyzing Quarter {i+1}: {start_date.date()} to {end_date.date()}...")
        
        res = optimize_range(df_1h, df_4h, df_1m, start_date, end_date)
        if res:
            res['Period'] = f"Q{i+1} ({start_date.date()}~{end_date.date()})"
            results.append(res)
        else:
            print(f"Skipping Q{i+1}: Not enough data or trades.")

    # Output Results
    print("\n" + "="*80)
    print(f"{'Period':<30} | {'Return':<8} | {'MDD':<8} | {'Eff':<5} | {'Vol':<4} | {'Trail':<5} | {'ADX':<3} | {'Don':<3} | {'Adapt':<5}")
    print("-"*80)
    for r in results:
        print(f"{r['Period']:<30} | {r['Return']:<8} | {r['MDD']:<8} | {r['Eff']:<5} | {r['Vol']:<4} | {r['Trail']:<5} | {r['ADX']:<3} | {r['Don']:<3} | {r['Adaptive']:<5}")
    print("="*80)

if __name__ == "__main__":
    main()
