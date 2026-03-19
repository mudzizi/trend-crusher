import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2
from src.config import CONFIG

def run_eth_detailed_backtest():
    # 1. ETH 최적 파라미터 (검증된 수치)
    symbol = "ETH/USDT"
    best_params = {
        "VOL_MULTIPLIER": 2.0,
        "TRAILING_ATR_MULT": 4.5,
        "RISK_PER_TRADE": 0.02,
        "EMA_TREND_PERIOD": 200,
        "SEED": 10000.0  # 초기 시드 10,000 USDT 기준
    }
    
    test_config = CONFIG.copy()
    test_config.update(best_params)
    test_config["SYMBOL"] = symbol
    
    # 2. 데이터 로드 (365일치)
    clean_sym = symbol.replace('/', '_')
    f_sig = f"data/{clean_sym}_1h.csv"
    f_trend = f"data/{clean_sym}_4h.csv"
    f_check = f"data/{clean_sym}_1m.csv"
    
    if not all(os.path.exists(f) for f in [f_sig, f_trend, f_check]):
        print("Error: Missing 365-day data. Please run data collection first.")
        return

    df_sig = pd.read_csv(f_sig)
    df_trend = pd.read_csv(f_trend)
    df_check = pd.read_csv(f_check)
    
    # 3. 전략 실행
    strategy = TrendCrusherV2(config=test_config)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)
    
    # 4. 상세 거래 데이터 가공
    detailed_trades = []
    initial_seed = test_config["SEED"]
    
    for i in range(0, len(trades), 2):
        if i + 1 < len(trades):
            o = trades[i]   # Open
            c = trades[i+1] # Close
            
            pnl_usdt = c['pnl_usdt']
            pnl_vs_seed = (pnl_usdt / initial_seed) * 100
            
            detailed_trades.append({
                'Open Time': o['time'],
                'Close Time': c['time'],
                'Side': o['side'],
                'Entry': round(o['price'], 2),
                'Exit': round(c['price'], 2),
                'PnL(%)': round(((c['price']/o['price'])-1)*100 if o['side']=='LONG' else (1-(c['price']/o['price']))*100, 2),
                'PnL(USDT)': round(pnl_usdt, 2),
                'Vs Seed(%)': round(pnl_vs_seed, 2)
            })

    df_report = pd.DataFrame(detailed_trades)
    
    print(f"\n🚀 ETH/USDT Detailed Backtest Report (Seed: {initial_seed:,.0f} USDT)")
    print("="*110)
    print(f"{'Open Time':<20} | {'Side':<5} | {'PnL(%)':>8} | {'PnL(USDT)':>12} | {'Vs Seed(%)':>10}")
    print("-" * 110)
    
    for idx, row in df_report.iterrows():
        print(f"{str(row['Open Time']):<20} | {row['Side']:<5} | {row['PnL(%)']:>7}% | {row['PnL(USDT)']:>12,.2f} | {row['Vs Seed(%)']:>9}%")
    
    print("="*110)
    final_cap = strategy.capital
    total_ret = ((final_cap / initial_seed) - 1) * 100
    print(f"Final Capital: {final_cap:,.2f} USDT | Total Return: {total_ret:+.2f}%")
    
    # CSV 저장
    df_report.to_csv("eth_detailed_trades.csv", index=False)
    print("\nDetailed report saved to 'eth_detailed_trades.csv'")

if __name__ == "__main__":
    run_eth_detailed_backtest()
