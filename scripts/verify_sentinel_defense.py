import pandas as pd
import numpy as np
import os
import asyncio
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.sentinel import MarketSentinel
from src.config import CONFIG

async def run_xrp_sentinel_test():
    symbol = "XRP/USDT"
    data_path = "data/XRP_USDT_2024_1m.csv"
    if not os.path.exists(data_path):
        print("XRP 2024 data not found.")
        return

    df_1m = pd.read_csv(data_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    
    # 1. Without Sentinel (기존)
    strategy_no = TrendCrusherV2(config=CONFIG)
    trades_no, _, _ = strategy_no.run_streaming_backtest(df_1m, risk_pct=0.05)
    ret_no = ((strategy_no.capital / strategy_no.initial_capital) - 1) * 100
    
    # 2. With Sentinel (신규)
    sentinel = MarketSentinel()
    strategy_yes = TrendCrusherV2(config=CONFIG)
    
    # Pre-calculate Chop Index for Sentinel
    df_1h = get_all_base_bars(df_1m, "1h")
    df_1h['chop'] = sentinel.calculate_choppiness(df_1h)
    
    # Use existing indicator calculation and join chop
    df_4h = get_all_base_bars(df_1m, "4h")
    df_ind = strategy_yes.calculate_indicators(df_1h, df_4h, CONFIG)
    df_ind['chop'] = df_1h.set_index('timestamp')['chop'].reindex(df_ind.index).ffill()
    
    # Run with sentinel hook
    trades_yes, _, _ = strategy_yes.run_streaming_backtest(
        df_1m, 
        risk_pct=0.05, 
        sentinel=sentinel, 
        pre_calculated_ind=df_ind
    )
    ret_yes = ((strategy_yes.capital / strategy_yes.initial_capital) - 1) * 100
    
    print("\n" + "="*50)
    print("XRP 2024 SENTINEL DEFENSE RESULT")
    print("="*50)
    print(f"NO SENTINEL:  Return {ret_no:.2f}% | Trades {len([t for t in trades_no if t['type']=='CLOSE'])}")
    print(f"WITH SENTINEL: Return {ret_yes:.2f}% | Trades {len([t for t in trades_yes if t['type']=='CLOSE'])}")
    print(f"DECREASED TRADES: {len(trades_no) - len(trades_yes)}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_xrp_sentinel_test())
