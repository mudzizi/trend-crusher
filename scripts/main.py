import pandas as pd
import numpy as np
import os
from src.strategy import TrendCrusherV2
from src.config import CONFIG

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def main():
    sym = CONFIG["SYMBOL"].replace('/', '_')
    f_sig = f"{CONFIG['DATA_DIR']}/{sym}_{CONFIG['SIGNAL_TIMEFRAME']}.csv"
    f_trend = f"{CONFIG['DATA_DIR']}/{sym}_{CONFIG['TREND_TIMEFRAME']}.csv"
    f_check = f"{CONFIG['DATA_DIR']}/{sym}_{CONFIG['CHECK_TIMEFRAME']}.csv"

    if not all(os.path.exists(f) for f in [f_sig, f_trend, f_check]):
        print("Required data missing. Please run data_fetcher.py first.")
        return

    df_sig = pd.read_csv(f_sig)
    df_trend = pd.read_csv(f_trend)
    df_check = pd.read_csv(f_check)

    strategy = TrendCrusherV2(config=CONFIG)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)

    if not trades:
        print("No trades executed.")
        return

    # --- 분석 및 리포트 데이터 생성 ---
    completed_trades = []
    for i in range(0, len(trades), 2):
        if i+1 < len(trades):
            o, c = trades[i], trades[i+1]
            raw_pnl_pct = ((c['price'] / o['price']) - 1) * 100
            actual_pnl_pct = raw_pnl_pct if o['side'] == 'LONG' else -raw_pnl_pct
            completed_trades.append({
                'open': o['time'], 'close': c['time'],
                'side': o['side'], 'pnl': actual_pnl_pct
            })

    final_cap = strategy.capital
    ret = ((final_cap / CONFIG["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    
    print("\n" + "="*80)
    print(f" [TrendCrusher] Final Backtest Report")
    print("="*80)
    print(f"Symbol: {CONFIG['SYMBOL']} | Total Return: {ret:.2f}% | MDD: {mdd:.2f}%")
    print(f"Trades: {len(completed_trades)} | Final Capital: {final_cap:,.2f} USDT")
    print("-" * 80)
    print(f"{'Open Time':<20} | {'Close Time':<20} | {'Side':<6} | {'PnL (%)'}")
    print("-" * 80)
    
    for t in completed_trades[-15:]:
        print(f"{str(t['open']):<20} | {str(t['close']):<20} | {t['side']:<6} | {t['pnl']:+.2f}%")
    print("="*80)

if __name__ == "__main__":
    main()
