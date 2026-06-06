import pandas as pd
import numpy as np
import os
import time
import optuna
from datetime import datetime, timedelta
import argparse
import sys

# 프로젝트 루트를 경로에 추가 (src 임포트 가능하게 함)
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

class UnifiedOptimizerV7:
    def __init__(self, df_1m, ind_cache, days):
        self.df_1m = df_1m
        self.ind_cache = ind_cache
        self.days = days
        self.strategy = TrendCrusherV2(config=CONFIG)

    def objective(self, trial):
        # 1. Hyperparameter Suggestions
        vol = trial.suggest_float("vol_mult", 0.5, 2.5, step=0.1) # Much lower floor
        trail = trial.suggest_float("atr_trail_mult", 2.5, 6.0, step=0.1)
        adx_val = trial.suggest_int("adx_threshold", 5, 25) # Lower ADX floor
        adx_4h_val = trial.suggest_int("adx_4h_threshold", 5, 25)
        chaos_val = trial.suggest_float("chaos_threshold", 0, 25, step=1) # Can disable chaos
        
        don = trial.suggest_categorical("donchian_period", [10, 20])
        ep = trial.suggest_categorical("ema_period", [50, 100, 200])
        be_guard = trial.suggest_float("be_guard_threshold", 0.0, 5.0, step=1.0)
        
        mode_choice = trial.suggest_categorical("mode", ["market", "sniper"])
        
        # 2. Run Backtest
        trades, equity_curve, _ = self.strategy.run_streaming_backtest(
            self.df_1m,
            vol_mult=vol, atr_trail_mult=trail, risk_pct=0.02,
            adx_threshold=adx_val, adx_4h_threshold=adx_4h_val,
            chaos_threshold=chaos_val,
            donchian_period=don, ema_period=ep,
            use_sniper=(mode_choice == "sniper"),
            be_guard_threshold=be_guard,
            use_adaptive=True,
            adaptive_steps=[{"pnl_pct": 10, "tighten_ratio": 0.6}, {"pnl_pct": 20, "tighten_ratio": 0.3}],
            pre_calculated_ind=self.ind_cache[(don, ep)]
        )
        
        ret = ((self.strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        # Extreme relaxation: just one full trade to be valid
        if len(trades) < 2: return -100.0, 100.0
        
        return ret, mdd

def run_optimization(symbol, days, trials):
    print(f"\n🚀 [V7.0-Permissive] Starting Optimization for {symbol}")
    print(f"📅 Period: {days} Days | Warmup: 60 Days | Trials: {trials}")
    
    fetcher = BinanceDataFetcher()
    total_days = days + 65
    try:
        fetcher.save_all(symbol=symbol, days=total_days)
    except:
        for tf in ["1h", "4h", "1m"]:
            fetcher.save_ohlcv(symbol, tf, days=total_days)
    
    clean_sym = symbol.replace('/', '_')
    df_1m_all = pd.read_csv(f"data/{clean_sym}_1m.csv", parse_dates=['timestamp'])
    
    print("📊 Pre-calculating indicators...")
    df_1h_all = get_all_base_bars(df_1m_all, "1h")
    df_4h_all = get_all_base_bars(df_1m_all, "4h")
    
    atr_all = calculate_atr(df_1h_all, 14)
    avg_vol_all = calculate_avg_vol(df_1h_all, 20)
    adx_all = calculate_adx(df_1h_all, 14)
    chop_all = calculate_choppiness(df_1h_all, 14)
    chaos_all = calculate_chaos_index(df_1h_all, 14)
    squeeze_all = calculate_squeeze_score(df_1h_all)
    adx_4h_all = calculate_adx(df_4h_all, 14)

    cutoff = datetime.now() - timedelta(days=days)
    df_1m_test = df_1m_all[df_1m_all['timestamp'] >= cutoff].copy()
    
    ind_cache = {}
    don_choices = [10, 20]
    ema_choices = [50, 100, 200]
    
    for dp in don_choices:
        for ep in ema_choices:
            df_ind = df_1h_all.copy()
            df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, dp)
            df_ind['atr'], df_ind['avg_vol'], df_ind['adx'], df_ind['chop'], df_ind['chaos'], df_ind['squeeze'] = \
                atr_all, avg_vol_all, adx_all, chop_all, chaos_all, squeeze_all
            
            df_4h_slim = df_4h_all[['timestamp']].copy()
            df_4h_slim['adx_4h'] = adx_4h_all
            df_ind = df_ind.merge(df_4h_slim, on='timestamp', how='left').ffill().fillna(0)
            
            df_ind['ema_h'] = calculate_ema(df_ind, ep * 4)
            df_ind['ema_slope'] = df_ind['ema_h'].diff(3)
            ind_cache[(dp, ep)] = df_ind[df_ind['timestamp'] >= cutoff].dropna()

    study = optuna.create_study(directions=["maximize", "minimize"])
    optimizer = UnifiedOptimizerV7(df_1m_test, ind_cache, days)
    study.optimize(optimizer.objective, n_trials=trials)

    best_trial = None
    max_eff = -999
    for trial in study.best_trials:
        ret, mdd = trial.values
        eff = ret / (mdd + 0.1)
        if eff > max_eff:
            max_eff, best_trial = eff, trial

    if best_trial:
        print(f"\n✅ BEST CONFIG FOUND for {symbol}")
        print(f"Efficiency: {max_eff:.2f} | Return: {best_trial.values[0]:.2f}% | MDD: {best_trial.values[1]:.2f}%")
        return {"Symbol": symbol, "Return": best_trial.values[0], "MDD": best_trial.values[1], "Eff": max_eff, **best_trial.params}
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="TRUMP/USDT")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--trials", type=int, default=100)
    args = parser.parse_args()
    
    symbols = args.symbol.split(',')
    all_results = []
    for s in symbols:
        res = run_optimization(s.strip().upper(), args.days, args.trials)
        if res: all_results.append(res)
    
    if all_results:
        os.makedirs("reports/optimization", exist_ok=True)
        summary_file = f"reports/optimization/golden_v7_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        pd.DataFrame(all_results).to_csv(summary_file, index=False)
        print(f"\n🏆 Results saved to: {summary_file}")

if __name__ == "__main__":
    main()
