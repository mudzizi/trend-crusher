import pandas as pd
import numpy as np
import os
import itertools
import time
import csv
import glob
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG

# --- [USER CONFIGURATION] ---
SYMBOLS = ["BTC_USDT", "SOL_USDT", "XRP_USDT", "TRUMP_USDT", "XAU_USDT"]
#SYMBOLS = ["ETH_USDT"]
QUARTERS = 4
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def load_completed_combos(base_dir):
    completed = set()
    csv_files = glob.glob(os.path.join(base_dir, "**", "*.csv"), recursive=True)
    for log_file in csv_files:
        try:
            df = pd.read_csv(log_file)
            if 'Adapt' in df.columns and 'Symbol' in df.columns:
                for _, row in df.iterrows():
                    key = (str(row['Symbol']), str(row['Quarter']), str(row['Mode']), float(row['Risk']), 
                           float(row['Vol']), float(row['Trail']), float(row['ADX']), int(row['Don']), str(row['Adapt']))
                    completed.add(key)
        except: continue
    return completed

def worker_task(task_args):
    try:
        data_1m, df_ind, combo, sym, quarter_name = task_args
        vol, trail, adx, don, risk, (m_name, sniper, retest), adapt = combo
        
        strategy = TrendCrusherV2(config=CONFIG)
        trades, equity_curve, _ = strategy.run_streaming_backtest(
            data_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=risk,
            adx_threshold=adx, donchian_period=don,
            use_sniper=sniper, retest_maker=retest,
            use_adaptive=len(adapt) > 0, adaptive_steps=adapt,
            pre_calculated_ind=df_ind
        )
        
        ret = ((strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        # Efficiency Score: Prioritize higher return with lower MDD
        efficiency = ret / (mdd + 0.1) if mdd > 0 else ret / 0.1
        
        return {
            "Symbol": sym, "Quarter": quarter_name, "Mode": m_name, "Risk": risk,
            "Vol": vol, "Trail": trail, "ADX": adx, "Don": don, "Adapt": "Yes" if len(adapt) > 0 else "No",
            "Return": round(ret, 2), "MDD": round(mdd, 2), "Eff": round(efficiency, 2), "Trades": len(trades)
        }
    except: return None

def optimize_symbol_quarter(sym, quarter_idx, df_1m, start_date, end_date, full_log_file, completed_set):
    q_name = f"Q{quarter_idx}"
    data_1m_filtered = df_1m[(df_1m['timestamp'] >= start_date) & (df_1m['timestamp'] < end_date)].copy()
    if len(data_1m_filtered) < 1440 * 3: return None # Min 3 days

    print(f"🚀 [{q_name}] Optimizing {sym} | {start_date.date()} ~ {end_date.date()}")

    # Grids
    vol_multipliers = [1.5, 2.0, 2.5]
    trailing_mults = [3.5, 4.5]
    adx_thresholds = [15, 20]
    donchian_periods = [10, 20]
    risk_pcts = [0.02, 0.05, 0.10]
    modes = [('Market', False, False), ('Sniper', True, False), ('Retest', False, True)]
    adaptive_options = [[], [{"pnl_pct": 2.0, "tighten_ratio": 0.5}], [{"pnl_pct": 5.0, "tighten_ratio": 0.7}]]
    
    # 1. Pre-calculation (Robust to short data)
    df_1h_base = get_all_base_bars(data_1m_filtered, "1h")
    df_4h_base = get_all_base_bars(data_1m_filtered, "4h")
    
    # Adaptive EMA Period
    ema_period = 200
    if len(df_4h_base) < ema_period:
        ema_period = max(10, len(df_4h_base) // 2)
    
    ema_values = calculate_ema(df_4h_base, ema_period)
    ema_s = pd.Series(ema_values.values, index=df_4h_base['timestamp'])
    ema_h = ema_s.reindex(df_1h_base['timestamp']).ffill().values
    
    atr = calculate_atr(df_1h_base, 14)
    avg_vol = calculate_avg_vol(df_1h_base, 20)
    adx = calculate_adx(df_1h_base, 14)
    
    ind_cache = {}
    for dp in donchian_periods:
        df_ind = df_1h_base.copy()
        df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, dp)
        df_ind['ema_h'], df_ind['atr'], df_ind['avg_vol'], df_ind['adx'] = ema_h, atr, avg_vol, adx
        # Drop only essential NaNs
        ind_cache[dp] = df_ind.dropna(subset=['upper', 'lower', 'atr', 'avg_vol', 'adx'])

    # 2. Tasks
    all_combos = list(itertools.product(vol_multipliers, trailing_mults, adx_thresholds, donchian_periods, risk_pcts, modes, adaptive_options))
    tasks = []
    for combo in all_combos:
        vol, trail, adx_val, don, risk, (m_name, sniper, retest), adapt = combo
        key = (str(sym), str(q_name), str(m_name), float(risk), float(vol), float(trail), float(adx_val), int(don), "Yes" if len(adapt) > 0 else "No")
        if key not in completed_set:
            tasks.append((data_1m_filtered, ind_cache[don], combo, sym, q_name))

    if not tasks: return None
    print(f"   - Testing {len(tasks)} new combinations...")
    
    best_res, best_eff = None, -9999
    completed = 0
    total_tasks = len(tasks)
    q_start_time = time.time()
    
    if not os.path.exists(full_log_file):
        with open(full_log_file, 'w', newline='') as f:
            csv.DictWriter(f, fieldnames=["Symbol", "Quarter", "Mode", "Risk", "Vol", "Trail", "ADX", "Don", "Adapt", "Return", "MDD", "Eff", "Trades"]).writeheader()

    with open(full_log_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["Symbol", "Quarter", "Mode", "Risk", "Vol", "Trail", "ADX", "Don", "Adapt", "Return", "MDD", "Eff", "Trades"])
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(worker_task, t): t for t in tasks}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    writer.writerow(res); f.flush(); os.fsync(f.fileno())
                    if res['Eff'] > best_eff and res['Trades'] >= 1: # Lowered trade limit for XAU
                        best_eff, best_res = res['Eff'], res
                
                completed += 1
                if completed % 50 == 0 or completed == total_tasks:
                    ts = datetime.now().strftime('%H:%M:%S')
                    elapsed = time.time() - q_start_time
                    print(f"   - [{ts}] Progress: {completed}/{total_tasks} ({completed/total_tasks*100:.1f}%) | Elapsed: {str(timedelta(seconds=int(elapsed)))}")
    return best_res

def main():
    start_time = time.time()
    base_repo_dir = "reports/mega_optimization"
    os.makedirs(base_repo_dir, exist_ok=True)
    completed_set = load_completed_combos(base_repo_dir)
    
    log_date = datetime.now().strftime('%Y%m%d_%H%M')
    session_dir = f"{base_repo_dir}/run_{log_date}"
    os.makedirs(session_dir, exist_ok=True)
    
    full_log_file = f"{session_dir}/full_details.csv"
    summary_file = f"{session_dir}/best_summary.csv"
    
    all_best_results = []
    for sym in SYMBOLS:
        print(f"\n{'='*20} STARTING SYMBOL: {sym} {'='*20}")
        data_path = f"data/{sym}_1m.csv"
        if not os.path.exists(data_path): continue
        df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
        latest_date = df_1m['timestamp'].max()
        
        for q in range(1, QUARTERS + 1):
            end_date = latest_date - timedelta(days=(q-1)*90)
            start_date = end_date - timedelta(days=90)
            best = optimize_symbol_quarter(sym, q, df_1m, start_date, end_date, full_log_file, completed_set)
            if best:
                all_best_results.append(best)
                pd.DataFrame(all_best_results).to_csv(summary_file, index=False)
                print(f"✅ Best for {sym} {best['Quarter']}: Return {best['Return']}% | Trades {best['Trades']}")

    duration = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"OPTIMIZATION COMPLETE! Results in: {session_dir}")
    print(f"Total Time Taken: {str(timedelta(seconds=int(duration)))}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
