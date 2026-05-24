import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

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

def run_eth_best_backtest():
    # 1. 스크린샷 설정과 동일하게 수정
    symbol = "ETH/USDT"
    best_params = {
        "VOL_MULTIPLIER": 2.0,
        "TRAILING_ATR_MULT": 4.5,
        "RISK_PER_TRADE": 0.02,
        "EMA_TREND_PERIOD": 200
    }
    
    # 설정 업데이트
    test_config = CONFIG.copy()
    test_config.update(best_params)
    test_config["SYMBOL"] = symbol
    
    # 2. 데이터 로드
    clean_sym = symbol.replace('/', '_')
    f_sig = f"data/{clean_sym}_1h.csv"
    f_trend = f"data/{clean_sym}_4h.csv"
    f_check = f"data/{clean_sym}_1m.csv"
    
    if not all(os.path.exists(f) for f in [f_sig, f_trend, f_check]):
        print(f"Error: Missing data files for {symbol}. Please check data/ directory.")
        return

    print(f"--- {symbol} Best Optimization Backtest ---")
    print(f"Params: Vol_Mult={best_params['VOL_MULTIPLIER']}, Trail={best_params['TRAILING_ATR_MULT']}, Risk={best_params['RISK_PER_TRADE']}, EMA={best_params['EMA_TREND_PERIOD']}")
    
    df_sig = pd.read_csv(f_sig)
    df_trend = pd.read_csv(f_trend)
    df_check = pd.read_csv(f_check)
    
    # 3. 전략 실행
    strategy = TrendCrusherV2(config=test_config)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)
    
    if not trades:
        print("No trades executed.")
        return
        
    # 4. 결과 분석 및 데이터 가공 (Visualizer용)
    processed_trades = []
    for i in range(0, len(trades), 2):
        if i+1 < len(trades):
            o, c = trades[i], trades[i+1]
            raw_pnl_pct = ((c['price'] / o['price']) - 1) * 100
            actual_pnl_pct = raw_pnl_pct if o['side'] == 'LONG' else -raw_pnl_pct
            processed_trades.append({
                'open_time': o['time'],
                'close_time': c['time'],
                'side': o['side'],
                'open_price': o['price'],
                'close_price': c['price'],
                'pnl_pct': actual_pnl_pct
            })
    
    trades_df = pd.DataFrame(processed_trades)
    
    # Equity history (Visualizer용)
    equity_df = pd.DataFrame([
        {'timestamp': df_sig.iloc[i]['timestamp'] if i < len(df_sig) else df_sig.iloc[-1]['timestamp'], 'balance': val}
        for i, val in enumerate(equity_curve)
    ])
    
    # 5. 시각화 리포트 생성
    from src.indicators import calculate_donchian, calculate_ema
    df_sig['upper'], df_sig['lower'] = calculate_donchian(df_sig, period=test_config["DONCHIAN_PERIOD"])
    df_sig['ema_h'] = calculate_ema(df_trend, period=test_config["EMA_TREND_PERIOD"]).reindex(df_sig.index).ffill()
    
    viz = TradingVisualizer(report_dir="reports")
    report_path = viz.generate_report(df_sig, trades_df, equity_df, symbol)
    
    # 6. 최종 성과 출력
    final_cap = strategy.capital
    ret = ((final_cap / test_config["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    
    print("\n" + "="*50)
    print(f" Result for {symbol}")
    print("="*50)
    print(f"Total Return: {ret:+.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Total Trades: {len(processed_trades)}")
    print(f"Final Capital: {final_cap:,.2f} USDT")
    print(f"Report Saved: {report_path}")
    print("="*50)

if __name__ == "__main__":
    run_eth_best_backtest()
