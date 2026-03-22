import pandas as pd
import numpy as np
import os
import itertools
import time
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor
from src.strategy import TrendCrusherV2
from src.config import CONFIG

# --- [USER CONFIGURATION] ---
SYMBOLS = ["ETH_USDT", "BTC_USDT", "SOL_USDT", "XRP_USDT", "TRUMP_USDT"]
QUARTERS = 4  # Number of 90-day periods to analyze
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def worker_task(task_args):
    """
    Function executed by each process.
    """
    data_1m, start_date, end_date, combo = task_args
    vol, trail, adx, don, risk, (m_name, sniper, retest), adapt = combo
    
    strategy = TrendCrusherV2(config=CONFIG)
    trades, equity_curve, _ = strategy.run_streaming_backtest(
        data_1m,
        vol_mult=vol,
        atr_trail_mult=trail,
        risk_pct=risk,
        adx_threshold=adx,
        donchian_period=don,
        use_sniper=sniper,
        retest_maker=retest,
        use_adaptive=len(adapt) > 0,
        adaptive_steps=adapt
    )
    
    if len(trades) >= 3:
        ret = ((strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        # Efficiency Score: Prioritize higher return with lower MDD
        efficiency = ret / (mdd + 0.1) if mdd > 0 else ret / 0.1
        return {
            "Efficiency": efficiency,
            "Return": ret,
            "MDD": mdd,
            "Trades": len(trades),
            "Config": {
                "Mode": m_name, "Risk": risk, "Vol": vol, "Trail": trail, 
                "ADX": adx, "Don": don, "Adapt": "Yes" if len(adapt) > 0 else "No",
                "Adapt_Steps": adapt
            }
        }
    return None

def optimize_symbol_quarter(sym, quarter_idx, df_1m, start_date, end_date):
    print(f"🚀 [Q{quarter_idx}] Optimizing {sym} | {start_date.date()} ~ {end_date.date()}")
    
    data_1m_filtered = df_1m[(df_1m['timestamp'] >= start_date) & (df_1m['timestamp'] < end_date)].copy()
    if len(data_1m_filtered) < 1440: return None

    # Comprehensive Grid
    vol_multipliers = [1.5, 2.0, 2.5, 3.0]
    trailing_mults = [2.5, 3.5, 4.5]
    adx_thresholds = [15, 20, 25]
    donchian_periods = [10, 20, 30]
    risk_pcts = [0.02, 0.05, 0.10]
    modes = [
        ('Market', False, False),
        ('Sniper', True, False),
        ('Retest', False, True)
    ]
    adaptive_options = [
        [], # None
        [{"pnl_pct": 2.0, "tighten_ratio": 0.5}], # Aggressive
        [{"pnl_pct": 5.0, "tighten_ratio": 0.7}], # Moderate
        [{"pnl_pct": 3.0, "tighten_ratio": 0.6}, {"pnl_pct": 10.0, "tighten_ratio": 0.4}] # Two-step
    ]
    
    combinations = list(itertools.product(vol_multipliers, trailing_mults, adx_thresholds, donchian_periods, risk_pcts, modes, adaptive_options))
    
    best_res = None
    max_workers = os.cpu_count() or 4
    
    # Prepare task list
    tasks = [(data_1m_filtered, start_date, end_date, combo) for combo in combinations]
    
    print(f"   - Testing {len(tasks)} combinations using {max_workers} cores...")
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(worker_task, tasks))
    
    # Filter and find best
    valid_results = [r for r in results if r is not None]
    if not valid_results: return None
    
    best_res = max(valid_results, key=lambda x: x['Efficiency'])
    return best_res

def main():
    os.makedirs("reports/mega_optimization", exist_ok=True)
    results_file = f"reports/mega_optimization/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    all_final_results = []
    
    for sym in SYMBOLS:
        print(f"\n{'='*20} STARTING SYMBOL: {sym} {'='*20}")
        data_path = f"data/{sym}_1m.csv"
        if not os.path.exists(data_path):
            print(f"❌ Data missing for {sym}, skipping...")
            continue
            
        df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
        latest_date = df_1m['timestamp'].max()
        
        for q in range(1, QUARTERS + 1):
            end_date = latest_date - timedelta(days=(q-1)*90)
            start_date = end_date - timedelta(days=90)
            
            best = optimize_symbol_quarter(sym, q, df_1m, start_date, end_date)
            
            if best:
                summary = {
                    "Symbol": sym,
                    "Quarter": f"Q{q}",
                    "Period": f"{start_date.date()}~{end_date.date()}",
                    "Return%": round(best['Return'], 2),
                    "MDD%": round(best['MDD'], 2),
                    "Eff": round(best['Efficiency'], 2),
                    "Trades": best['Trades'],
                    **best['Config']
                }
                all_final_results.append(summary)
                # Intermediate save
                pd.DataFrame(all_final_results).to_csv(results_file, index=False)
                print(f"✅ Best for {sym} Q{q}: Return {summary['Return%']}% | MDD {summary['MDD%']}% | Mode: {summary['Mode']}")
            else:
                print(f"⚠️ No valid results for {sym} Q{q}")

    print(f"\n{'='*60}")
    print(f"OVERNIGHT OPTIMIZATION COMPLETE!")
    print(f"Full results saved to: {results_file}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
