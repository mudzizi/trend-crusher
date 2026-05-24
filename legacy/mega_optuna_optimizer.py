import pandas as pd
import numpy as np
import os
import time
import csv
import optuna
from datetime import datetime, timedelta
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

# --- [USER CONFIGURATION] ---
SYMBOLS = ["TRUMP/USDT", "ETH/USDT"]
DAYS_TO_OPTIMIZE = 365
TRIALS_PER_QUARTER = 100  # 365일 데이터를 대상으로 100회 정밀 탐색
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

class OptunaOptimizer:
    def __init__(self, data_1m, ind_cache, symbol, quarter_name):
        self.data_1m = data_1m
        self.ind_cache = ind_cache
        self.symbol = symbol
        self.quarter_name = quarter_name
        self.strategy = TrendCrusherV2(config=CONFIG)

    def objective(self, trial):
        # 1. Suggest Parameters
        vol = trial.suggest_float("vol_mult", 1.2, 3.5, step=0.1)
        trail = trial.suggest_float("atr_trail_mult", 2.5, 6.0, step=0.1)
        adx_val = trial.suggest_int("adx_threshold", 0, 35) # ADX 0부터 탐색
        don = trial.suggest_categorical("donchian_period", [10, 20, 30])
        ep = trial.suggest_categorical("ema_period", [50, 100, 200])
        risk = trial.suggest_float("risk_pct", 0.02, 0.05, step=0.01)
        
        mode_choice = trial.suggest_categorical("mode", ["Market", "Sniper", "Retest"])
        sniper = (mode_choice == "Sniper")
        retest = (mode_choice == "Retest")
        
        adapt_choice = trial.suggest_categorical("adapt_type", ["None", "Tight", "Aggressive", "BreakEven"])
        adapt = []
        if adapt_choice == "Tight":
            adapt = [{"pnl_pct": 2.0, "tighten_ratio": 0.5},{"pnl_pct":5.0,"tighten_ratio":0.3}]
        elif adapt_choice == "Aggressive":
            adapt = [{"pnl_pct": 5.0, "tighten_ratio": 0.5},{"pnl_pct":8.0, "tighten_ratio":0.3}]
        elif adapt_choice == "BreakEven":
            # 1% 수익 시 즉시 본절가+0.1%로 가드 (ATR 배수를 0.01 정도로 극단적으로 낮춤)
            adapt = [{"pnl_pct": 1.0, "atr_mult": 0.1}]

        # 2. Run Backtest
        trades, equity_curve, _ = self.strategy.run_streaming_backtest(
            self.data_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=risk,
            adx_threshold=adx_val, donchian_period=don,
            ema_period=ep,
            use_sniper=sniper, retest_maker=retest,
            use_adaptive=(adapt_choice != "None"), adaptive_steps=adapt,
            pre_calculated_ind=self.ind_cache[(don, ep)]
        )
        
        ret = ((self.strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        if len(trades) < 4:
            return -100.0, 100.0

        return ret, mdd

def optimize_symbol_quarter(sym, quarter_idx, df_1m, start_date, end_date, summary_file):
    q_name = str(quarter_idx)
    data_1m_filtered = df_1m[(df_1m['timestamp'] >= start_date) & (df_1m['timestamp'] < end_date)].copy()
    if len(data_1m_filtered) < 1440 * 3: return None

    print(f"🚀 [{q_name}] Optuna Optimizing {sym} (ADX 0+ Search) | {start_date.date()} ~ {end_date.date()}")

    donchian_periods = [10, 20, 30]
    ema_periods = [50, 100, 200]
    df_1h_base = get_all_base_bars(data_1m_filtered, "1h")
    df_4h_base = get_all_base_bars(data_1m_filtered, "4h")
    
    ema_cache = {}
    for ep in ema_periods:
        actual_ep = ep
        if len(df_4h_base) < ep: actual_ep = max(10, len(df_4h_base) // 2)
        ema_values = calculate_ema(df_4h_base, actual_ep)
        ema_s = pd.Series(ema_values.values, index=df_4h_base['timestamp'])
        ema_cache[ep] = ema_s.reindex(df_1h_base['timestamp']).ffill().values
    
    atr = calculate_atr(df_1h_base, 14)
    avg_vol = calculate_avg_vol(df_1h_base, 20)
    adx = calculate_adx(df_1h_base, 14)
    
    ind_cache = {}
    for dp in donchian_periods:
        for ep in ema_periods:
            df_ind = df_1h_base.copy()
            df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, dp)
            df_ind['ema_h'], df_ind['atr'], df_ind['avg_vol'], df_ind['adx'] = ema_cache[ep], atr, avg_vol, adx
            ind_cache[(dp, ep)] = df_ind.dropna(subset=['upper', 'lower', 'atr', 'avg_vol', 'adx'])

    study = optuna.create_study(directions=["maximize", "minimize"])
    optimizer = OptunaOptimizer(data_1m_filtered, ind_cache, sym, q_name)
    study.optimize(optimizer.objective, n_trials=TRIALS_PER_QUARTER)

    best_trial = None
    max_eff = -999
    for trial in study.best_trials:
        ret, mdd = trial.values
        eff = ret / (mdd + 0.1)
        if eff > max_eff:
            max_eff = eff
            best_trial = trial

    if best_trial:
        p = best_trial.params
        res = {
            "Symbol": sym, "Period": q_name, "Mode": p['mode'], "Risk": p['risk_pct'],
            "Vol": p['vol_mult'], "Trail": p['atr_trail_mult'], "ADX": p['adx_threshold'], 
            "Don": p['donchian_period'], "EMA": p['ema_period'], "Adapt": p['adapt_type'],
            "Return": round(best_trial.values[0], 2), "MDD": round(best_trial.values[1], 2), 
            "Eff": round(max_eff, 2)
        }
        return res
    return None

def main():
    start_time = time.time()
    base_repo_dir = "reports/optuna_optimization"
    os.makedirs(base_repo_dir, exist_ok=True)
    
    log_date = datetime.now().strftime('%Y%m%d_%H%M')
    session_dir = f"{base_repo_dir}/run_adx_zero_{log_date}"
    os.makedirs(session_dir, exist_ok=True)
    
    summary_file = f"{session_dir}/optuna_summary.csv"
    
    all_best_results = []
    fetcher = BinanceDataFetcher()

    for sym in SYMBOLS:
        print(f"\n{'='*20} STARTING SYMBOL: {sym} {'='*20}")
        fetcher.save_all(symbol=sym, days=DAYS_TO_OPTIMIZE + 10)
        
        clean_sym = sym.replace('/', '_')
        data_path = f"data/{clean_sym}_1m.csv"
        if not os.path.exists(data_path): continue
            
        df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
        cutoff = datetime.now() - timedelta(days=DAYS_TO_OPTIMIZE)
        df_1m = df_1m[df_1m['timestamp'] >= cutoff].copy()
        
        if df_1m.empty: continue

        earliest_date = df_1m['timestamp'].min()
        latest_date = df_1m['timestamp'].max()
        
        best = optimize_symbol_quarter(sym, "Last90D", df_1m, earliest_date, latest_date + timedelta(seconds=1), summary_file)
        if best:
            all_best_results.append(best)
            pd.DataFrame(all_best_results).to_csv(summary_file, index=False)
            print(f"✅ Best Result (ADX={best['ADX']}): Return {best['Return']}% | MDD {best['MDD']}%")

    duration = time.time() - start_time
    print(f"\nOptimization Complete! Results in: {session_dir}")

if __name__ == "__main__":
    main()
