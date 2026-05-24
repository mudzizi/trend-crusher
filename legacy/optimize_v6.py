import pandas as pd
import numpy as np
import os
import time
import csv
import optuna
from datetime import datetime, timedelta
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx, calculate_choppiness
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

# --- [USER CONFIGURATION] ---
SYMBOLS = ["ETH/USDT", "TRUMP/USDT"]
DAYS_TO_OPTIMIZE = 365
TRIALS_PER_QUARTER = 100 
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

class OptunaOptimizerV6:
    def __init__(self, data_1m, ind_cache, symbol):
        self.data_1m = data_1m
        self.ind_cache = ind_cache
        self.symbol = symbol
        self.strategy = TrendCrusherV2(config=CONFIG)

    def objective(self, trial):
        # 1. Suggest Parameters
        vol = trial.suggest_float("vol_mult", 1.2, 3.0, step=0.1)
        trail = trial.suggest_float("atr_trail_mult", 3.0, 6.0, step=0.1)
        adx_val = trial.suggest_int("adx_threshold", 10, 30)
        adx_4h_val = trial.suggest_int("adx_4h_threshold", 10, 30)
        don = trial.suggest_categorical("donchian_period", [10, 15, 20])
        ep = trial.suggest_categorical("ema_period", [50, 100, 200])
        be_guard = trial.suggest_float("be_guard_threshold", 0.0, 5.0, step=0.5)
        
        mode_choice = trial.suggest_categorical("mode", ["Market", "Sniper"])
        sniper = (mode_choice == "Sniper")
        
        # 2. Run Backtest
        trades, equity_curve, _ = self.strategy.run_streaming_backtest(
            self.data_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=0.02,
            adx_threshold=adx_val, adx_4h_threshold=adx_4h_val,
            donchian_period=don, ema_period=ep,
            use_sniper=sniper, be_guard_threshold=be_guard,
            use_adaptive=True,
            adaptive_steps=[{"pnl_pct": 15, "tighten_ratio": 0.6}, {"pnl_pct": 30, "tighten_ratio": 0.3}],
            pre_calculated_ind=self.ind_cache[(don, ep)]
        )
        
        ret = ((self.strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        if len(trades) < 10: # Minimum trades over a year
            return -100.0, 100.0

        return ret, mdd

def run_v6_optimization():
    print(f"🚀 Starting V6.0 Optuna Optimization (365 Days)...")
    fetcher = BinanceDataFetcher()
    base_dir = "reports/optuna_v6"
    os.makedirs(base_dir, exist_ok=True)
    summary_file = f"{base_dir}/v6_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    results = []
    for sym in SYMBOLS:
        print(f"\n{'='*20} SYMBOL: {sym} {'='*20}")
        fetcher.save_all(symbol=sym, days=DAYS_TO_OPTIMIZE + 10)
        
        clean_sym = sym.replace('/', '_')
        df_1m = pd.read_csv(f"data/{clean_sym}_1m.csv", parse_dates=['timestamp'])
        cutoff = datetime.now() - timedelta(days=DAYS_TO_OPTIMIZE)
        df_1m = df_1m[df_1m['timestamp'] >= cutoff].copy()
        
        # Pre-calculation for V6.0
        don_choices = [10, 15, 20]
        ema_choices = [50, 100, 200]
        
        print("📊 Pre-calculating indicators for V6.0...")
        df_1h_base = get_all_base_bars(df_1m, "1h")
        df_4h_base = get_all_base_bars(df_1m, "4h")
        
        atr = calculate_atr(df_1h_base, 14)
        avg_vol = calculate_avg_vol(df_1h_base, 20)
        adx = calculate_adx(df_1h_base, 14)
        chop = calculate_choppiness(df_1h_base, 14)
        adx_4h = calculate_adx(df_4h_base, 14)
        
        ind_cache = {}
        for dp in don_choices:
            for ep in ema_choices:
                df_ind = df_1h_base.copy()
                df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, dp)
                df_ind['atr'], df_ind['avg_vol'], df_ind['adx'], df_ind['chop'] = atr, avg_vol, adx, chop
                
                # MTF ADX
                df_4h_slim = df_4h_base[['timestamp']].copy()
                df_4h_slim['adx_4h'] = adx_4h
                df_ind = df_ind.merge(df_4h_slim, on='timestamp', how='left').ffill().fillna(0)
                
                # Slope
                df_ind['ema_h'] = calculate_ema(df_ind, ep * 4)
                df_ind['ema_slope'] = df_ind['ema_h'].diff(3)
                
                ind_cache[(dp, ep)] = df_ind.dropna()

        study = optuna.create_study(directions=["maximize", "minimize"])
        optimizer = OptunaOptimizerV6(df_1m, ind_cache, sym)
        study.optimize(optimizer.objective, n_trials=TRIALS_PER_QUARTER)

        best_trial = None
        max_eff = -999
        for trial in study.best_trials:
            ret, mdd = trial.values
            eff = ret / (mdd + 0.1)
            if eff > max_eff:
                max_eff, best_trial = eff, trial

        if best_trial:
            p = best_trial.params
            res = {"Symbol": sym, "Return": best_trial.values[0], "MDD": best_trial.values[1], "Eff": max_eff, **p}
            results.append(res)
            pd.DataFrame(results).to_csv(summary_file, index=False)
            print(f"✅ Best: {max_eff:.2f} Eff | {best_trial.values[0]:.2f}% Ret")

if __name__ == "__main__":
    run_v6_optimization()
