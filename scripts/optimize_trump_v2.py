import pandas as pd
import numpy as np
import os
import time
import optuna
from datetime import datetime, timedelta
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG

# --- [CONFIGURATION] ---
SYMBOL = "TRUMP_USDT"
TRIALS = 50 
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

class OptunaOptimizer:
    def __init__(self, data_1m, ind_cache):
        self.data_1m = data_1m
        self.ind_cache = ind_cache
        self.strategy = TrendCrusherV2(config=CONFIG)

    def objective(self, trial):
        # 1. Suggest Parameters
        vol = trial.suggest_float("vol_mult", 1.5, 3.5, step=0.1)
        trail = trial.suggest_float("atr_trail_mult", 3.0, 6.0, step=0.1)
        adx_val = trial.suggest_int("adx_threshold", 15, 45)
        don = trial.suggest_categorical("donchian_period", [10, 20, 30])
        ep = trial.suggest_categorical("ema_period", [50, 100, 200])
        risk = trial.suggest_float("risk_pct", 0.02, 0.05, step=0.01)
        
        mode_choice = trial.suggest_categorical("mode", ["Market", "Sniper"])
        sniper = (mode_choice == "Sniper")
        
        adapt_choice = trial.suggest_categorical("adapt_type", ["None", "Tight", "Aggressive"])
        adapt = []
        if adapt_choice == "Tight":
            adapt = [{"pnl_pct": 2.0, "tighten_ratio": 0.5},{"pnl_pct":5.0,"tighten_ratio":0.3}]
        elif adapt_choice == "Aggressive":
            adapt = [{"pnl_pct": 5.0, "tighten_ratio": 0.5},{"pnl_pct":8.0, "tighten_ratio":0.3}]

        # 2. Run Backtest
        trades, equity_curve, _ = self.strategy.run_streaming_backtest(
            self.data_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=risk,
            adx_threshold=adx_val, donchian_period=don,
            ema_period=ep,
            use_sniper=sniper,
            use_adaptive=(adapt_choice != "None"), adaptive_steps=adapt,
            pre_calculated_ind=self.ind_cache[(don, ep)]
        )
        
        ret = ((self.strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        if len(trades) < 4: # Minimum 2 full trades
            return -100.0, 100.0

        return ret, mdd

def run_optimization():
    print(f"🚀 Starting Targeted Optuna Optimization for {SYMBOL}...")
    data_path = f"data/{SYMBOL}_1m.csv"
    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found.")
        return

    df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
    
    # Pre-calculation for all trials
    donchian_periods = [10, 20, 30]
    ema_periods = [50, 100, 200]
    df_1h_base = get_all_base_bars(df_1m, "1h")
    df_4h_base = get_all_base_bars(df_1m, "4h")
    
    print("📊 Pre-calculating indicators...")
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
    optimizer = OptunaOptimizer(df_1m, ind_cache)
    
    study.optimize(optimizer.objective, n_trials=TRIALS)

    print("\n" + "="*50)
    print(f" Optimization Result for {SYMBOL}")
    print("="*50)
    
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
        print(f"Best Efficiency: {max_eff:.2f}")
        print(f"Return: {best_trial.values[0]:.2f}%")
        print(f"MDD: {best_trial.values[1]:.2f}%")
        print("\nOptimal Parameters:")
        for k, v in p.items():
            print(f"  {k}: {v}")
    else:
        print("No successful trials found.")

if __name__ == "__main__":
    run_optimization()
