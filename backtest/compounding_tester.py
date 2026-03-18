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

def run_comparison(symbol, vol_mult, trail_mult, risk):
    clean_sym = symbol.replace('/', '_')
    df_1h = pd.read_csv(f"data/{clean_sym}_1h.csv")
    df_4h = pd.read_csv(f"data/{clean_sym}_4h.csv")
    df_1m = pd.read_csv(f"data/{clean_sym}_1m.csv")

    # 1. 복리 (Compounding)
    strategy_comp = TrendCrusherV2(config=CONFIG)
    trades_comp, curve_comp = strategy_comp.run_precision_backtest(
        df_1h, df_4h, df_1m, vol_mult=vol_mult, atr_trail_mult=trail_mult, risk_pct=risk
    )
    ret_comp = ((strategy_comp.capital / CONFIG["INITIAL_CAPITAL"]) - 1) * 100
    mdd_comp = calculate_mdd(curve_comp) * 100

    # 2. 단리 (Simple Interest)
    class SimpleStrategy(TrendCrusherV2):
        def calculate_position_size(self, price, stop_loss_price, risk_pct):
            risk_amt = self.initial_capital * risk_pct # Always use initial capital
            stop_dist = abs(price - stop_loss_price)
            return risk_amt / stop_dist if stop_dist > 0 else 0

    strategy_simple = SimpleStrategy(config=CONFIG)
    trades_simple, curve_simple = strategy_simple.run_precision_backtest(
        df_1h, df_4h, df_1m, vol_mult=vol_mult, atr_trail_mult=trail_mult, risk_pct=risk
    )
    ret_simple = ((strategy_simple.capital / CONFIG["INITIAL_CAPITAL"]) - 1) * 100
    mdd_simple = calculate_mdd(curve_simple) * 100

    return {
        "Symbol": symbol,
        "Simple Ret(%)": round(ret_simple, 2),
        "Comp Ret(%)": round(ret_comp, 2),
        "Simple MDD(%)": round(mdd_simple, 2),
        "Comp MDD(%)": round(mdd_comp, 2),
        "Trades": len(trades_comp)//2
    }

if __name__ == "__main__":
    print("Comparing Simple Interest vs Compounding...")
    eth_res = run_comparison("ETH/USDT", 2.0, 4.0, 0.02)
    trump_res = run_comparison("TRUMP/USDT", 2.5, 4.0, 0.02)
    
    df_res = pd.DataFrame([eth_res, trump_res])
    print("\n" + "="*80)
    print(" [Power of Compounding Comparison: 1-Year Report] ")
    print("="*80)
    print(df_res.to_string(index=False))
    print("="*80)
    print("\n* Compounding (복리): Reinvests all profits into next trades.")
    print("* Simple Interest (단리): Always risks based on the original 10,000 USDT.")
