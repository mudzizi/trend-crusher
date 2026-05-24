import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# 프로젝트 루트를 경로에 추가 (src 임포트 가능하게 함)
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.visualizer import TradingVisualizer

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_all_v4_backtests():
    symbols = ["TRUMP/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"]
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
    
    summary_results = []

    for symbol in symbols:
        print(f"\n🚀 Testing V4.0 Asymmetric for {symbol} (365 Days)...")
        
        # 1. 설정 및 데이터 로드
        test_config = CONFIG.copy()
        test_config.update(v4_params)
        test_config["SYMBOL"] = symbol
        
        clean_sym = symbol.replace('/', '_')
        f_check = f"data/{clean_sym}_1m.csv"
        
        if not os.path.exists(f_check):
            print(f"⚠️ Missing data file {f_check}")
            continue

        df_check = pd.read_csv(f_check)
        df_check['timestamp'] = pd.to_datetime(df_check['timestamp'])
        
        cutoff = datetime.now() - timedelta(days=365)
        df_check = df_check[df_check['timestamp'] >= cutoff].copy()
        
        # 2. 전략 실행
        strategy = TrendCrusherV2(config=test_config)
        trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_check)
        
        if not trades:
            print(f"No trades for {symbol}")
            continue
            
        final_cap = strategy.capital
        ret = ((final_cap / test_config["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        
        summary_results.append({
            "Symbol": symbol,
            "Return": f"{ret:+.2f}%",
            "MDD": f"{mdd:.2f}%",
            "Trades": len(trades) // 2
        })

    # 최종 결과 출력
    print("\n" + "="*60)
    print(" 🏁 V4.0 CROSS-SYMBOL VALIDATION SUMMARY (365D) ")
    print("="*60)
    print(pd.DataFrame(summary_results).to_string(index=False))
    print("="*60)

if __name__ == "__main__":
    run_all_v4_backtests()
