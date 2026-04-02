import pandas as pd
import numpy as np
import asyncio
import os
from datetime import datetime
from src.strategy import TrendCrusherV2
from src.config import CONFIG

async def run_simulation_for_symbol(symbol, settings):
    clean_sym = symbol.replace('/', '_')
    
    # Load 1m data (for streaming)
    data_path = f"data/{clean_sym}_1m.csv"
    if not os.path.exists(data_path):
        print(f"❌ Data file not found for {symbol}: {data_path}")
        return

    print(f"\n--- Starting Simulation for {symbol} (Unified Settings) ---")
    df_1m = pd.read_csv(data_path)
    
    # Limit to last 365 days or maximum available
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m = df_1m.dropna(subset=['timestamp'])
    
    cutoff = df_1m['timestamp'].max() - pd.Timedelta(days=365)
    df_1m = df_1m[df_1m['timestamp'] > cutoff].reset_index(drop=True)
    
    if df_1m.empty:
        print(f"❌ No data available for {symbol} in the requested period.")
        return

    print(f"Using {len(df_1m)} mins of data (from {df_1m['timestamp'].min()} to {df_1m['timestamp'].max()})")
    
    strategy = TrendCrusherV2(config=CONFIG)
    
    from src.visualizer import TradingVisualizer
    
    trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_1m, **settings)
    
    final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
    
    # Calculate MDD properly
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    mdd = np.max(drawdown) * 100
    
    print(f"✅ {symbol} Simulation Finished.")
    print(f"Final Return: {final_return:+.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    
    # --- Save Results ---
    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    mode_str = "Sniper_Mode" # All unified to Sniper

    output_dir = os.path.join("reports", clean_sym, mode_str, now_str)
    os.makedirs(output_dir, exist_ok=True)

    viz = TradingVisualizer()
    img_filename = f"report_{clean_sym}_{mode_str}_{now_str}.png"
    img_path = os.path.join(output_dir, img_filename)
    temp_img_path = viz.generate_comprehensive_report(df_ind, trades, equity_curve, symbol, params=settings)
    os.rename(temp_img_path, img_path)

    df_trades = pd.DataFrame(trades)
    csv_path = os.path.join(output_dir, f"trades_{clean_sym}_{now_str}.csv")
    df_trades.to_csv(csv_path, index=False)

    summary_path = os.path.join(output_dir, f"summary_{clean_sym}_{now_str}.txt")
    with open(summary_path, "w") as f:
        f.write(f"Backtest Summary: {symbol}\n")
        f.write(f"Mode: {mode_str}\n")
        f.write(f"Final Return: {final_return:.2f}%\n")
        f.write(f"Max Drawdown: {mdd:.2f}%\n")
        f.write(f"Total Trades: {len(df_trades[df_trades['type']=='CLOSE'])}\n")
        f.write(f"Settings: {settings}\n")

    return {"symbol": symbol, "return": final_return, "mdd": mdd}

async def main():
    # Unified settings based on TRUMP's best configuration
    unified_settings = {
        'use_sniper': True,
        'retest_maker': False,
        'vol_mult': 2.2,
        'atr_trail_mult': 4.5,
        'ema_period': 100,
        'risk_pct': 0.08,
        'use_adaptive': True,
        'adaptive_steps': [
            {"pnl_pct": 5.0, "tighten_ratio": 0.5},
            {"pnl_pct": 8.0, "tighten_ratio": 0.3}
        ]
    }

    targets = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "TRUMP/USDT"]
    
    results = []
    for symbol in targets:
        res = await run_simulation_for_symbol(symbol, unified_settings)
        if res: results.append(res)
    
    print("\n" + "="*50)
    print(f" UNIFIED SETTINGS SIMULATION (TRUMP BASE) ")
    print(f"{'SYMBOL':<12} | {'RETURN':>12} | {'MDD':>10}")
    print("-" * 50)
    for r in results:
        print(f"{r['symbol']:<12} | {r['return']:>11.2f}% | {r['mdd']:>9.2f}%")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
