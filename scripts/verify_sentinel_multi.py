import pandas as pd
import numpy as np
import os
import asyncio
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.sentinel import MarketSentinel
from src.config import CONFIG

async def run_sentinel_comparison(symbol, data_path, risk_pct=0.05):
    if not os.path.exists(data_path):
        print(f"Data not found for {symbol} at {data_path}")
        return None

    df_1m = pd.read_csv(data_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    
    # 1. Without Sentinel
    strategy_no = TrendCrusherV2(config=CONFIG)
    trades_no, _, _ = strategy_no.run_streaming_backtest(df_1m, risk_pct=risk_pct)
    ret_no = ((strategy_no.capital / strategy_no.initial_capital) - 1) * 100
    
    # 2. With Sentinel
    sentinel = MarketSentinel()
    strategy_yes = TrendCrusherV2(config=CONFIG)
    
    df_1h = get_all_base_bars(df_1m, "1h")
    df_1h['chop'] = sentinel.calculate_choppiness(df_1h)
    df_4h = get_all_base_bars(df_1m, "4h")
    df_ind = strategy_yes.calculate_indicators(df_1h, df_4h, CONFIG)
    df_ind['chop'] = df_1h.set_index('timestamp')['chop'].reindex(df_ind.index).ffill()
    
    trades_yes, _, _ = strategy_yes.run_streaming_backtest(
        df_1m, risk_pct=risk_pct, sentinel=sentinel, pre_calculated_ind=df_ind
    )
    ret_yes = ((strategy_yes.capital / strategy_yes.initial_capital) - 1) * 100
    
    return {
        "Symbol": symbol,
        "Ret_No": ret_no,
        "Ret_Yes": ret_yes,
        "Trades_No": len([t for t in trades_no if t['type']=='CLOSE']),
        "Trades_Yes": len([t for t in trades_yes if t['type']=='CLOSE']),
        "Diff_Ret": ret_yes - ret_no
    }

async def main():
    # 2024 Full for BTC, ETH, XRP
    # Recent 365d for TRUMP (since it didn't exist in early 2024)
    tasks = [
        run_sentinel_comparison("BTC/USDT (2024)", "data/BTC_USDT_2024_1m.csv"),
        run_sentinel_comparison("ETH/USDT (2024)", "data/ETH_USDT_2024_1m.csv"),
        run_sentinel_comparison("XRP/USDT (2024)", "data/XRP_USDT_2024_1m.csv"),
        run_sentinel_comparison("TRUMP/USDT (Recent)", "data/TRUMP_USDT_1m.csv")
    ]
    
    results = await asyncio.gather(*tasks)
    results = [r for r in results if r]
    
    print("\n" + "="*70)
    print(f"{'Symbol':<20} | {'No Sentinel':<12} | {'With Sentinel':<12} | {'Diff'}")
    print("-" * 70)
    for r in results:
        print(f"{r['Symbol']:<20} | {r['Ret_No']:>10.2f}% | {r['Ret_Yes']:>11.2f}% | {r['Diff_Ret']:>+6.2f}%p")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
