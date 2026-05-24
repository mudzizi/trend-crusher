import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2, get_all_base_bars
from src.config import CONFIG

def run_historical_1h_test(symbol):
    print(f"\n🚀 Running Historical 1h Test for {symbol} (2024-2025)...")
    
    clean_sym = symbol.replace('/', '_')
    f_hist = f"data/{clean_sym}_1h_hist_2024.csv"
    
    if not os.path.exists(f_hist):
        print(f"⚠️ History file {f_hist} not found.")
        return

    df_1h = pd.read_csv(f_hist, parse_dates=['timestamp'])
    
    # MTF를 위해 4시간봉 생성
    df_4h = df_1h.set_index('timestamp').resample('4h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()

    v4_params = {
        "VOL_MULTIPLIER": 2.2,
        "TRAILING_ATR_MULT": 5.0,
        "RISK_PER_TRADE": 0.02,
        "EMA_TREND_PERIOD": 50,
        "DONCHIAN_PERIOD": 10,
        "ADX_FILTER_LEVEL": 20.0,
        "ADX_4H_THRESHOLD": 20.0,
        "INITIAL_SL_ATR": 2.0,
        "BE_GUARD_THRESHOLD": 0.0,
        "USE_ADAPTIVE_TRAIL": True,
        "ADAPTIVE_TRAIL_STEPS": [
            {"pnl_pct": 15, "atr_mult": 3.0}, 
            {"pnl_pct": 30, "atr_mult": 1.5}
        ]
    }
    
    test_config = CONFIG.copy()
    test_config.update(v4_params)
    test_config["SYMBOL"] = symbol
    
    strategy = TrendCrusherV2(config=test_config)
    
    # 1시간봉 기반 정밀 시뮬레이션 (1m이 없을 경우 대안)
    # run_streaming_backtest에 1시간봉 데이터를 넣으면 1시간 단위로 시뮬레이션합니다.
    trades, equity_curve, _ = strategy.run_streaming_backtest(df_1h)
    
    if not trades:
        print(f"No trades executed for {symbol}")
        return

    final_cap = strategy.capital
    ret = ((final_cap / test_config["SEED"]) - 1) * 100
    
    # MDD 계산
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    mdd = np.max((peak - curve) / (peak + 1e-10)) * 100

    print(f"--- {symbol} 2024-2025 Result ---")
    print(f"Total Return: {ret:+.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Total Trades: {len(trades) // 2}")
    print(f"Final Capital: {final_cap:,.2f} USDT")

if __name__ == "__main__":
    run_historical_1h_test("ETH/USDT")
    run_historical_1h_test("SOL/USDT")
