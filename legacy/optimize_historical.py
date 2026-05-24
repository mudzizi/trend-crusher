import pandas as pd
import numpy as np
import os
import optuna
from datetime import datetime, timedelta
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG

# --- [CONFIGURATION] ---
SYMBOL = "ETH/USDT"
TRIALS = 50 
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

class OptunaOptimizer:
    def __init__(self, data_1h, ind_cache):
        self.data_1h = data_1h
        self.ind_cache = ind_cache
        self.strategy = TrendCrusherV2(config=CONFIG)

    def objective(self, trial):
        vol = trial.suggest_float("vol_mult", 1.0, 3.0, step=0.1)
        trail = trial.suggest_float("atr_trail_mult", 3.0, 6.0, step=0.1)
        adx_val = trial.suggest_int("adx_threshold", 10, 30)
        ep = trial.suggest_categorical("ema_period", [50, 100, 200])
        
        # 2. Run Backtest (Using 1h data as 'streaming' data)
        trades, equity_curve, _ = self.strategy.run_streaming_backtest(
            self.data_1h,
            vol_mult=vol, atr_trail_mult=trail,
            adx_threshold=adx_val,
            ema_period=ep,
            pre_calculated_ind=self.ind_cache[ep]
        )
        
        ret = ((self.strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        if len(trades) < 6: return -100.0, 100.0
        return ret, mdd

def run_historical_optimization():
    print(f"🚀 Optimizing for {SYMBOL} (Historical 2024-2025)...")
    clean_sym = SYMBOL.replace('/', '_')
    data_path = f"data/{clean_sym}_1h_hist_2024.csv"
    
    df_1h = pd.read_csv(data_path, parse_dates=['timestamp'])
    
    # Pre-calculation
    ema_periods = [50, 100, 200]
    df_4h = df_1h.set_index('timestamp').resample('4h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()
    
    ind_cache = {}
    for ep in ema_periods:
        df_ind = df_1h.copy()
        df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, 10)
        df_ind['atr'] = calculate_atr(df_ind, 14)
        df_ind['avg_vol'] = calculate_avg_vol(df_ind, 20)
        df_ind['adx'] = calculate_adx(df_ind, 14)
        
        # 4h ADX for MTF
        df_4h['adx_4h'] = calculate_adx(df_4h, 14)
        df_ind = df_ind.merge(df_4h[['timestamp', 'adx_4h']], on='timestamp', how='left').ffill().fillna(0)
        
        # Smooth EMA
        df_ind['ema_h'] = calculate_ema(df_ind, period=ep*4)
        ind_cache[ep] = df_ind.dropna()

    study = optuna.create_study(directions=["maximize", "minimize"])
    optimizer = OptunaOptimizer(df_1h, ind_cache)
    study.optimize(optimizer.objective, n_trials=TRIALS)

    for trial in study.best_trials:
        print(f"Best: Return {trial.values[0]:.2f}% | MDD {trial.values[1]:.2f}% | Params: {trial.params}")

if __name__ == "__main__":
    run_historical_optimization()
