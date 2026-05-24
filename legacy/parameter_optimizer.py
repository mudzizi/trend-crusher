import pandas as pd
import numpy as np
import os
import itertools
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_parameter_search():
    # 1. 대상 심볼 설정
    symbols = ['ETH/USDT', 'TRUMP/USDT', 'XAU/USDT', 'SOL/USDT']
    
    # 2. 탐색할 파라미터 그리드 (수익률 복구를 위해 범위를 넓힘)
    vol_multipliers = [1.5, 2.0, 2.5]
    adx_filters = [15, 20, 25]
    ema_periods = [100, 200]
    
    # 고정 파라미터 (V3 검증된 기본값)
    trailing_mult = 4.5
    risk_pct = 0.02

    CONFIG["BACKTEST_DAYS"] = 365
    results = []

    combinations = list(itertools.product(symbols, vol_multipliers, adx_filters, ema_periods))
    total_runs = len(combinations)
    
    print(f"🚀 Starting V3 Parameter Optimization: Total {total_runs} combinations...")

    for i, (sym, vol, adx, ema) in enumerate(combinations):
        current_config = CONFIG.copy()
        current_config.update({
            "SYMBOL": sym,
            "VOL_MULTIPLIER": vol,
            "ADX_FILTER_LEVEL": adx,
            "EMA_TREND_PERIOD": ema,
            "TRAILING_ATR_MULT": trailing_mult,
            "RISK_PER_TRADE": risk_pct,
            "USE_ADAPTIVE_TRAIL": True, # V3 핵심 기능 활성화
            "ADAPTIVE_TRAIL_STEPS": [{"pnl_pct": 10, "atr_mult": 3.5}, {"pnl_pct": 20, "atr_mult": 2.5}]
        })

        clean_sym = sym.replace('/', '_')
        f_sig = f"{current_config['DATA_DIR']}/{clean_sym}_{current_config['SIGNAL_TIMEFRAME']}.csv"
        f_trend = f"{current_config['DATA_DIR']}/{clean_sym}_{current_config['TREND_TIMEFRAME']}.csv"
        f_check = f"{current_config['DATA_DIR']}/{clean_sym}_{current_config['CHECK_TIMEFRAME']}.csv"

        if not all(os.path.exists(f) for f in [f_sig, f_trend, f_check]):
            fetcher = BinanceDataFetcher(config=current_config)
            fetcher.save_all()

        df_sig = pd.read_csv(f_sig)
        df_trend = pd.read_csv(f_trend)
        df_check = pd.read_csv(f_check)

        strategy = TrendCrusherV2(config=current_config)
        trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)

        if trades:
            ret = ((strategy.capital / current_config["SEED"]) - 1) * 100
            mdd = calculate_mdd(equity_curve) * 100
            efficiency = ret / mdd if mdd > 0.1 else 0
            
            results.append({
                "Symbol": sym,
                "Vol_Mult": vol,
                "ADX_Filter": adx,
                "EMA_Period": ema,
                "Return(%)": round(ret, 2),
                "MDD(%)": round(mdd, 2),
                "Efficiency": round(efficiency, 2),
                "Trades": len(trades) // 2
            })
        
        if (i+1) % 10 == 0:
            print(f"Progress: {i+1}/{total_runs} combinations tested.")

    if not results:
        print("No results found.")
        return

    df_results = pd.DataFrame(results)
    best_results = df_results.loc[df_results.groupby("Symbol")["Efficiency"].idxmax()]
    
    print("\n" + "="*85)
    print(" [Ultimate Optimization Result: Best Parameters Per Symbol] ")
    print("="*85)
    print(best_results.to_string(index=False))
    
    best_results.to_csv("best_parameters_report.csv", index=False)
    df_results.to_csv("mega_optimization_raw_results.csv", index=False)
    print("\nReports saved: 'best_parameters_report.csv' & 'mega_optimization_raw_results.csv'")

if __name__ == "__main__":
    run_parameter_search()
