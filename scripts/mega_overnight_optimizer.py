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

def get_adapt_name(adapt):
    if not adapt:
        return "No"
    try:
        steps = []
        for step in adapt:
            pnl = step.get("pnl_pct", 0)
            ratio = step.get("tighten_ratio", 0)
            steps.append(f"P{pnl}T{ratio}")
        return "|".join(steps)
    except:
        return "Yes"

# --- [USER CONFIGURATION] ---
SYMBOLS = ["XRP_USDT", "TRUMP_USDT", "SUI_USDT"]
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
            if 'Adapt' in df.columns and 'Symbol' in df.columns and 'SL_ATR' in df.columns:
                for _, row in df.iterrows():
                    key = (str(row['Symbol']), str(row['Quarter']), str(row['Mode']), float(row['Risk']), 
                           float(row['Vol']), float(row['Trail']), float(row['ADX']), int(row['Don']), 
                           str(row['Adapt']), float(row['SL_ATR']), float(row['BE_Guard']), float(row['Chaos_Th']), int(row['EMA_P']))
                    completed.add(key)
        except: continue
    return completed

def worker_task(task_args):
    try:
        data_1m, df_ind, combo, sym, quarter_name = task_args
        vol, trail, adx, don, risk, (m_name, sniper, retest), adapt, sl_atr, be_guard, chaos, ema_p = combo
        
        strategy = TrendCrusherV2(config=CONFIG)
        trades, equity_curve, _ = strategy.run_streaming_backtest(
            data_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=risk,
            adx_threshold=adx, donchian_period=don,
            use_sniper=sniper, retest_maker=retest,
            use_adaptive=len(adapt) > 0, adaptive_steps=adapt,
            initial_sl_atr=sl_atr, be_guard_threshold=be_guard,
            chaos_threshold=chaos, ema_period=ema_p,
            pre_calculated_ind=df_ind
        )
        
        ret = ((strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        # Efficiency Score: Prioritize higher return with lower MDD
        efficiency = ret / (mdd + 0.1) if mdd > 0 else ret / 0.1
        
        return {
            "Symbol": sym, "Quarter": quarter_name, "Mode": m_name, "Risk": risk,
            "Vol": vol, "Trail": trail, "ADX": adx, "Don": don, "Adapt": get_adapt_name(adapt),
            "SL_ATR": sl_atr, "BE_Guard": be_guard, "Chaos_Th": chaos, "EMA_P": ema_p,
            "Return": round(ret, 2), "MDD": round(mdd, 2), "Eff": round(efficiency, 2), "Trades": len(trades)
        }
    except: return None

def optimize_symbol_quarter(sym, quarter_idx, df_1m, start_date, end_date, full_log_file, completed_set):
    q_name = f"Q{quarter_idx}"
    data_1m_filtered = df_1m[(df_1m['timestamp'] >= start_date) & (df_1m['timestamp'] < end_date)].copy()
    if len(data_1m_filtered) < 1440 * 3: return None # Min 3 days

    print(f"🚀 [{q_name}] Optimizing {sym} | {start_date.date()} ~ {end_date.date()}")

    # Grids
    if sym == "XRP_USDT":
        # 필수 파라미터 고정 (이전 최상위 분석 반영)
        vol_multipliers = [2.2]
        be_guard_thresholds = [3.0]
        donchian_periods = [20]
        risk_pcts = [0.08]
        modes = [('Sniper', True, False)]  # Sniper 모드 고정
        adaptive_options = [[]]            # Adapt=No 고정
        initial_sl_atrs = [2.0]            # 가속을 위해 중간값 고정
        chaos_thresholds = [20.0]          # 중간값 고정
        
        # 경계값 추가 범위 확장
        adx_thresholds = [10, 15, 20]      # 하향 확장 (20 -> 10, 15 추가)
        trailing_mults = [2.5, 3.0, 3.5]   # 하향 확장 (3.5 -> 2.5, 3.0 추가)
        ema_trend_periods = [150, 200, 250] # 상향 확장 (150 -> 200, 250 추가)
        
    elif sym == "TRUMP_USDT":
        # 필수 파라미터 고정 (이전 최상위 분석 반영)
        donchian_periods = [20]
        risk_pcts = [0.10]
        modes = [('Market', False, False), ('Retest', False, True)] # Market, Retest 유효
        adaptive_options = [
            [{"pnl_pct": 2.0, "tighten_ratio": 0.5}, {"pnl_pct": 2.0, "tighten_ratio": 0.3}],
            [{"pnl_pct": 5.0, "tighten_ratio": 0.5}, {"pnl_pct": 8.0, "tighten_ratio": 0.3}]
        ]  # Adapt=Yes 고정 (두 가지 옵션 제공)
        initial_sl_atrs = [2.0]            # 가속을 위해 중간값 고정
        
        # 경계값 추가 범위 확장
        vol_multipliers = [1.0, 1.2, 1.5]  # 하향 확장 (1.5 -> 1.0, 1.2 추가)
        trailing_mults = [4.5, 5.0, 5.5]   # 상향 확장 (4.5 -> 5.0, 5.5 추가)
        adx_thresholds = [30, 35, 40]      # 상향 확장 (30 -> 35, 40 추가)
        be_guard_thresholds = [1.0, 1.5, 2.0] # 하향 확장 (2.0 -> 1.0, 1.5 추가)
        chaos_thresholds = [5.0, 10.0, 15.0] # 하향 확장 (15.0 -> 5.0, 10.0 추가)
        ema_trend_periods = [150, 200, 250] # 상향 확장 (150 -> 200, 250 추가)
        
    elif sym == "SUI_USDT":
        # 필수 파라미터 고정 (이전 Q1 최상위 분석 반영)
        modes = [('Market', False, False)]  # Market 모드 고정
        risk_pcts = [0.10]                  # Risk=0.10 고정
        donchian_periods = [20]             # Don=20 고정
        adaptive_options = [[]]            # Adapt=No 고정
        initial_sl_atrs = [1.5]            # SL_ATR=1.5 고정
        be_guard_thresholds = [3.0]        # BE_Guard=3.0 고정
        chaos_thresholds = [20.0]          # 중간값 고정

        # 경계값 추가 범위 확장
        vol_multipliers = [2.8, 3.2, 3.6]  # 상향 확장 (2.8 -> 3.2, 3.6 추가)
        trailing_mults = [4.5, 5.0, 5.5]   # 상향 확장 (4.5 -> 5.0, 5.5 추가)
        adx_thresholds = [30, 35, 40]      # 상향 확장 (30 -> 35, 40 추가)
        ema_trend_periods = [25, 50, 75]   # 하향 확장 (50 -> 25, 75 추가)

    else:
        vol_multipliers = [1.5, 2.2, 2.8]
        trailing_mults = [3.5, 4.5]
        adx_thresholds = [20, 30]
        donchian_periods = [10, 20]
        risk_pcts = [0.03, 0.05, 0.08, 0.10]
        modes = [('Market', False, False), ('Sniper', True, False), ('Retest', False, True)]
        adaptive_options = [[], 
                            [{"pnl_pct": 2.0, "tighten_ratio": 0.5},{"pnl_pct": 2.0, "tighten_ratio":0.3}],
                            [{"pnl_pct": 5.0, "tighten_ratio": 0.5},{"pnl_pct": 8.0, "tighten_ratio":0.3}]
                            ]
        initial_sl_atrs = [1.5, 2.0, 2.5]
        be_guard_thresholds = [2.0, 3.0, 4.0]
        chaos_thresholds = [15.0, 20.0, 25.0]
        ema_trend_periods = [50, 100, 150]
    
    # 1. Pre-calculation (Robust to short data)
    df_1h_base = get_all_base_bars(data_1m_filtered, "1h")
    df_4h_base = get_all_base_bars(data_1m_filtered, "4h")
    
    strategy = TrendCrusherV2(config=CONFIG)
    
    ind_cache = {}
    for dp in donchian_periods:
        for ep in ema_trend_periods:
            cur_ep = ep
            if len(df_4h_base) < (cur_ep * 4):
                cur_ep = max(3, len(df_4h_base) // 8)
                
            test_cfg = CONFIG.copy()
            test_cfg.update({
                "DONCHIAN_PERIOD": dp,
                "EMA_TREND_PERIOD": cur_ep
            })
            df_ind = strategy.calculate_indicators(df_1h_base, df_4h_base, test_cfg)
            # Drop essential NaNs for indicator stability
            ind_cache[(dp, ep)] = df_ind.dropna(subset=['upper', 'lower', 'atr', 'avg_vol', 'adx', 'chop', 'chaos', 'squeeze', 'ema_h'])

    # 2. Tasks
    all_combos = list(itertools.product(
        vol_multipliers, trailing_mults, adx_thresholds, donchian_periods, 
        risk_pcts, modes, adaptive_options, initial_sl_atrs, be_guard_thresholds, 
        chaos_thresholds, ema_trend_periods
    ))
    tasks = []
    for combo in all_combos:
        vol, trail, adx_val, don, risk, (m_name, sniper, retest), adapt, sl_atr, be_guard, chaos, ema_p = combo
        key = (str(sym), str(q_name), str(m_name), float(risk), float(vol), float(trail), float(adx_val), int(don), 
               get_adapt_name(adapt), float(sl_atr), float(be_guard), float(chaos), int(ema_p))
        if key not in completed_set:
            tasks.append((data_1m_filtered, ind_cache[(don, ema_p)], combo, sym, q_name))

    if not tasks: return None
    print(f"   - Testing {len(tasks)} new combinations...")
    
    best_res, best_eff = None, -9999
    completed = 0
    total_tasks = len(tasks)
    q_start_time = time.time()
    
    fields = ["Symbol", "Quarter", "Mode", "Risk", "Vol", "Trail", "ADX", "Don", "Adapt", "SL_ATR", "BE_Guard", "Chaos_Th", "EMA_P", "Return", "MDD", "Eff", "Trades"]
    
    if not os.path.exists(full_log_file):
        with open(full_log_file, 'w', newline='') as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()

    with open(full_log_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(worker_task, t): t for t in tasks}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    writer.writerow(res); f.flush(); os.fsync(f.fileno())
                    if res['Eff'] > best_eff and res['Trades'] >= 1:
                        best_eff, best_res = res['Eff'], res
                
                completed += 1
                if completed % 100 == 0 or completed == total_tasks:
                    ts = datetime.now().strftime('%H:%M:%S')
                    elapsed = time.time() - q_start_time
                    print(f"   - [{ts}] Progress: {completed}/{total_tasks} ({completed/total_tasks*100:.1f}%) | Elapsed: {str(timedelta(seconds=int(elapsed)))}")
    return best_res

def main():
    start_time = time.time()
    base_repo_dir = "reports/mega_optimization_v2"
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
