import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2
from src.config import CONFIG

def run_comprehensive_test(symbol):
    print(f"\n{'='*60}")
    print(f"🌍 Running V5.0 Comprehensive 2-Year Test for {symbol}")
    print(f"{'='*60}")
    
    clean_sym = symbol.replace('/', '_')
    f_hist_2024 = f"data/{clean_sym}_1h_hist_2024.csv" # 2024-2025
    f_current = f"data/{clean_sym}_1h.csv"             # 2025-2026
    
    # 1. 데이터 통합
    dfs = []
    if os.path.exists(f_hist_2024):
        dfs.append(pd.read_csv(f_hist_2024, parse_dates=['timestamp']))
    if os.path.exists(f_current):
        dfs.append(pd.read_csv(f_current, parse_dates=['timestamp']))
        
    if not dfs:
        print(f"⚠️ No data files found for {symbol}")
        return

    df_full = pd.concat(dfs).sort_values('timestamp').drop_duplicates(subset=['timestamp']).reset_index(drop=True)
    print(f"📅 Total Period: {df_full['timestamp'].min()} ~ {df_full['timestamp'].max()} ({len(df_full)} hours)")

    # 2. V7.0 설정 (카오스 & 에너지 폭발 모드)
    v7_params = {
        "VOL_MULTIPLIER": 1.5,       # Chaos/Squeeze가 있으므로 기본 문턱 낮춤
        "TRAILING_ATR_MULT": 5.0,
        "RISK_PER_TRADE": 0.02,
        "EMA_TREND_PERIOD": 50,
        "DONCHIAN_PERIOD": 10,
        "ADX_FILTER_LEVEL": 20.0,
        "ADX_4H_THRESHOLD": 15.0,
        "INITIAL_SL_ATR": 2.0,
        "INITIAL_SL_PCT": 0.0,
        "BE_GUARD_THRESHOLD": 2.0,
        "USE_ADAPTIVE_TRAIL": True,
        "ADAPTIVE_TRAIL_STEPS": []
    }
    
    test_config = CONFIG.copy()
    test_config.update(v7_params)
    test_config["SYMBOL"] = symbol
    
    strategy = TrendCrusherV2(config=test_config)
    
    # 3. 전략 실행 (1시간봉 정밀 스트리밍 시뮬레이션)
    trades, equity_curve, _ = strategy.run_streaming_backtest(df_full)
    
    if not trades:
        print(f"No trades for {symbol}")
        return

    final_cap = strategy.capital
    ret = ((final_cap / test_config["SEED"]) - 1) * 100
    
    # MDD 계산
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    mdd = np.max((peak - curve) / (peak + 1e-10)) * 100

    print(f"\n--- {symbol} V5.0 FINAL RESULT ---")
    print(f"Total Return: {ret:+.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Total Trades: {len(trades) // 2}")
    print(f"Efficiency (Ret/MDD): {ret/(mdd+0.1):.2f}")
    print(f"Final Capital: {final_cap:,.2f} USDT")

if __name__ == "__main__":
    test_symbols = ["ETH/USDT", "SOL/USDT", "XRP/USDT", "TRUMP/USDT"]
    for sym in test_symbols:
        run_comprehensive_test(sym)
