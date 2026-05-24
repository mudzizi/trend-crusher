import pandas as pd
import numpy as np
import os
import time
import optuna
from datetime import datetime, timedelta
import argparse
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx, calculate_choppiness, calculate_chaos_index, calculate_squeeze_score
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

class UnifiedOptimizer:
    def __init__(self, df_1m, ind_cache):
        self.df_1m = df_1m
        self.ind_cache = ind_cache
        self.strategy = TrendCrusherV2(config=CONFIG)

    def objective(self, trial):
        # Hyperparameter Suggestions
        vol = trial.suggest_float("vol_mult", 1.2, 3.0, step=0.1)
        trail = trial.suggest_float("atr_trail_mult", 3.0, 6.0, step=0.1)
        adx_val = trial.suggest_int("adx_threshold", 10, 30)
        adx_4h_val = trial.suggest_int("adx_4h_threshold", 10, 30)
        don = trial.suggest_categorical("donchian_period", [10, 15, 20])
        ep = trial.suggest_categorical("ema_period", [50, 100, 200])
        be_guard = trial.suggest_float("be_guard_threshold", 0.0, 5.0, step=0.5)
        
        mode_choice = trial.suggest_categorical("mode", ["market", "sniper"])
        
        # Run Backtest
        trades, equity_curve, _ = self.strategy.run_streaming_backtest(
            self.df_1m,
            vol_mult=vol, atr_trail_mult=trail,
            adx_threshold=adx_val, adx_4h_threshold=adx_4h_val,
            donchian_period=don, ema_period=ep,
            use_sniper=(mode_choice == "sniper"),
            be_guard_threshold=be_guard,
            use_adaptive=True,
            adaptive_steps=[{"pnl_pct": 15, "tighten_ratio": 0.6}, {"pnl_pct": 30, "tighten_ratio": 0.3}],
            pre_calculated_ind=self.ind_cache[(don, ep)]
        )
        
        ret = ((self.strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        if len(trades) < 10: return -100.0, 100.0
        return ret, mdd

def run_optimization(symbol, days, trials):
    print(f"\n🚀 Starting Unified Optimization for {symbol} | {days} Days | {trials} Trials")
    
    fetcher = BinanceDataFetcher()
    fetcher.save_all(symbol=symbol, days=days + 10)
    
    clean_sym = symbol.replace('/', '_')
    df_1m = pd.read_csv(f"data/{clean_sym}_1m.csv", parse_dates=['timestamp'])
    cutoff = datetime.now() - timedelta(days=days)
    df_1m = df_1m[df_1m['timestamp'] >= cutoff].copy()
    
    print("📊 Pre-calculating indicators for optimization...")
    df_1h_base = get_all_base_bars(df_1m, "1h")
    df_4h_base = get_all_base_bars(df_1m, "4h")
    
    atr = calculate_atr(df_1h_base, 14)
    avg_vol = calculate_avg_vol(df_1h_base, 20)
    adx = calculate_adx(df_1h_base, 14)
    chop = calculate_choppiness(df_1h_base, 14)
    chaos = calculate_chaos_index(df_1h_base, 14)
    squeeze = calculate_squeeze_score(df_1h_base)
    adx_4h = calculate_adx(df_4h_base, 14)
    
    ind_cache = {}
    don_choices = [10, 15, 20]
    ema_choices = [50, 100, 200]
    for dp in don_choices:
        for ep in ema_choices:
            df_ind = df_1h_base.copy()
            df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, dp)
            df_ind['atr'], df_ind['avg_vol'], df_ind['adx'], df_ind['chop'], df_ind['chaos'], df_ind['squeeze'] = \
                atr, avg_vol, adx, chop, chaos, squeeze
            
            df_4h_slim = df_4h_base[['timestamp']].copy()
            df_4h_slim['adx_4h'] = adx_4h
            df_ind = df_ind.merge(df_4h_slim, on='timestamp', how='left').ffill().fillna(0)
            
            df_ind['ema_h'] = calculate_ema(df_ind, ep * 4)
            df_ind['ema_slope'] = df_ind['ema_h'].diff(3)
            ind_cache[(dp, ep)] = df_ind.dropna()

    study = optuna.create_study(directions=["maximize", "minimize"])
    optimizer = UnifiedOptimizer(df_1m, ind_cache)
    study.optimize(optimizer.objective, n_trials=trials)

    best_trial = None
    max_eff = -999
    for trial in study.best_trials:
        ret, mdd = trial.values
        eff = ret / (mdd + 0.1)
        if eff > max_eff:
            max_eff, best_trial = eff, trial

    if best_trial:
        print(f"\n✅ Optimization Complete for {symbol}")
        print(f"Best Efficiency: {max_eff:.2f} | Return: {best_trial.values[0]:.2f}% | MDD: {best_trial.values[1]:.2f}%")
        print("Optimal Parameters:", best_trial.params)
        return {"Symbol": symbol, "Return": best_trial.values[0], "MDD": best_trial.values[1], "Eff": max_eff, **best_trial.params}
    return None

def main():
    parser = argparse.ArgumentParser(description="TrendCrusher V7.0 Unified Parameter Optimizer")
    parser.add_argument("--symbol", type=str, default="ETH/USDT", help="Symbol or comma-separated list")
    parser.add_argument("--days", type=int, default=365, help="Days of data to optimize over")
    parser.add_argument("--trials", type=int, default=100, help="Number of trials per symbol")
    
    args = parser.parse_args()
    symbols = args.symbol.split(',')
    
    all_results = []
    for s in symbols:
        res = run_optimization(s.strip().upper(), args.days, args.trials)
        if res: all_results.append(res)
    
    if all_results:
        os.makedirs("reports/optimization", exist_ok=True)
        summary_file = f"reports/optimization/summary_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        pd.DataFrame(all_results).to_csv(summary_file, index=False)
        print(f"\n📊 Global Summary saved to: {summary_file}")

if __name__ == "__main__":
    main()
