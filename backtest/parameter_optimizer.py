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
    # 1. 최신 거래대금 상위 20개 코인으로 업데이트
    symbols = [
        'BTC/USDT', 'ETH/USDT', 'ALPACA/USDT', 'SOL/USDT', 'XAG/USDT', 
        'XAU/USDT', 'XRP/USDT', 'HYPE/USDT', 'ZEC/USDT', 'DOGE/USDT', 
        'SIREN/USDT', 'BNX/USDT', 'BARD/USDT', 'BNB/USDT', '1000PEPE/USDT', 
        'RIVER/USDT', 'PIPPIN/USDT', 'ALPHA/USDT', 'ENJ/USDT', 'PAXG/USDT'
    ]
    vol_multipliers = [1.5, 2.0, 2.5]
    trailing_mults = [3.5, 4.0, 4.5]
    risks = [0.02] # 리스크 2% 고정
    ema_periods = [100, 200]

    # CONFIG의 BACKTEST_DAYS를 365로 강제 설정
    CONFIG["BACKTEST_DAYS"] = 365

    results = []

    combinations = list(itertools.product(symbols, vol_multipliers, trailing_mults, risks, ema_periods))
    total_runs = len(combinations)
    
    print(f"Starting Mega Grid Search: Total {total_runs} combinations...")

    for i, (sym, vol, trail, risk, ema) in enumerate(combinations):
        current_config = CONFIG.copy()
        current_config.update({
            "SYMBOL": sym,
            "VOL_MULTIPLIER": vol,
            "TRAILING_ATR_MULT": trail,
            "RISK_PER_TRADE": risk,
            "EMA_TREND_PERIOD": ema
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
        trades, equity_curve = strategy.run_precision_backtest(
            df_sig, df_trend, df_check, 
            vol_mult=vol, 
            atr_trail_mult=trail,
            risk_pct=risk,
            ema_period=ema
        )

        if trades:
            ret = ((strategy.capital / current_config["SEED"]) - 1) * 100
            mdd = calculate_mdd(equity_curve) * 100
            efficiency = ret / mdd if mdd > 0.1 else 0
            
            results.append({
                "Symbol": sym,
                "Vol_Mult": vol,
                "Trail_Mult": trail,
                "Risk": risk,
                "EMA_Period": ema,
                "Return(%)": round(ret, 2),
                "MDD(%)": round(mdd, 2),
                "Efficiency": round(efficiency, 2),
                "Trades": len(trades) // 2
            })
        
        if (i+1) % 5 == 0:
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
