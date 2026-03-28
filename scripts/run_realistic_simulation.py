import pandas as pd
import numpy as np
import asyncio
import os
from datetime import datetime
from src.strategy import TrendCrusherV2
from src.config import CONFIG

async def run_realistic_simulation():
    symbol = "TRUMP/USDT"
    clean_sym = symbol.replace('/', '_')
    
    # Load 1m data (for streaming)
    print("Loading 1m data for realistic simulation...")
    df_1m = pd.read_csv(f"data/{clean_sym}_1m.csv")
    
    # Limit to last 365 days or maximum available
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m = df_1m.dropna(subset=['timestamp']) # Ensure no NaNs in timestamp
    
    cutoff = df_1m['timestamp'].max() - pd.Timedelta(days=365)
    df_1m = df_1m[df_1m['timestamp'] > cutoff].reset_index(drop=True)
    
    if df_1m.empty:
        print("❌ No data available for the requested period. Check your data files.")
        return

    print(f"Using {len(df_1m)} mins of data (from {df_1m['timestamp'].min()} to {df_1m['timestamp'].max()})")
    
    strategy = TrendCrusherV2(config=CONFIG)
    
    # Run Streaming Backtest
    print(f"\n🚀 [Streaming Simulation] {symbol} (Max Available Period)")
    
    # Injecting optimized TRUMP settings (v11.8.0 equivalent)
    kwargs = {
        'use_sniper': False,
        'retest_maker': False,
        'vol_mult': 2.0,
        'atr_trail_mult': 5.0,
        'ema_period': 100,
        'risk_pct': 0.05,
        'use_adaptive': True,
        'adaptive_steps': [
            {"pnl_pct": 2.0, "tighten_ratio": 0.8},
            {"pnl_pct": 5.0, "tighten_ratio": 0.5},
            {"pnl_pct": 8.0, "tighten_ratio": 0.3}
        ]
    }

    
    from src.visualizer import TradingVisualizer
    
    trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_1m, **kwargs)
    
    final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
    
    # Calculate MDD properly
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    mdd = np.max(drawdown) * 100
    
    print(f"\n✅ Simulation Finished.")
    print(f"Final Return: {final_return:+.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    
    # --- Save Results in Structured Directory ---
    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    mode_str = "Retest_Maker" if kwargs['retest_maker'] else ("Sniper_Mode" if kwargs['use_sniper'] else "Market_Mode")

    # Structure: reports/{SYMBOL}/{MODE}/{TIMESTAMP}/
    output_dir = os.path.join("reports", clean_sym, mode_str, now_str)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Generate Visual Report (Comprehensive Image)
    viz = TradingVisualizer()
    img_filename = f"report_{clean_sym}_{mode_str}_{now_str}.png"
    img_path = os.path.join(output_dir, img_filename)

    # We need to temporarily change TradingVisualizer behavior or just move the file
    # For simplicity, we'll use the existing method and move the result
    temp_img_path = viz.generate_comprehensive_report(df_ind, trades, equity_curve, symbol, params=kwargs)
    os.rename(temp_img_path, img_path)
    print(f"🎨 Comprehensive visual report saved to: {img_path}")

    # 2. Save Trade Logs to CSV
    df_trades = pd.DataFrame(trades)
    csv_path = os.path.join(output_dir, f"trades_{clean_sym}_{now_str}.csv")
    df_trades.to_csv(csv_path, index=False)
    print(f"📂 Detailed trades saved to: {csv_path}")

    # 3. Save Equity Curve for Dashboard Visualization
    df_equity = pd.DataFrame({
        'timestamp': pd.date_range(start=df_1m['timestamp'].min(), periods=len(equity_curve), freq='D'),
        'equity': equity_curve
    })
    equity_path = os.path.join(output_dir, f"equity_{clean_sym}_{now_str}.csv")
    df_equity.to_csv(equity_path, index=False)

    # 4. Generate Summary Report
    summary_path = os.path.join(output_dir, f"summary_{clean_sym}_{now_str}.txt")
    with open(summary_path, "w") as f:
        f.write(f"Backtest Summary: {symbol}\n")
        f.write(f"Mode: {mode_str}\n")
        f.write(f"Period: {df_1m['timestamp'].min()} to {df_1m['timestamp'].max()}\n")
        f.write(f"Final Return: {final_return:.2f}%\n")
        f.write(f"Max Drawdown: {mdd:.2f}%\n")
        f.write(f"Total Trades: {len(df_trades[df_trades['type']=='CLOSE'])}\n")
        f.write(f"Settings: {kwargs}\n")

    print(f"📊 Summary report generated: {summary_path}")


if __name__ == "__main__":
    asyncio.run(run_realistic_simulation())
