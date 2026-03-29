import pandas as pd
import numpy as np
import asyncio
import os
from datetime import datetime
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.visualizer import TradingVisualizer

async def run_robust_simulation(symbol, risk_pct):
    clean_sym = symbol.replace('/', '_')
    print(f"\n🚀 STARTING SIMULATION: {symbol} | RISK: {risk_pct*100}%")
    
    # Load 1m data
    data_path = f"data/{clean_sym}_1m.csv"
    if not os.path.exists(data_path):
        print(f"⚠️ Data not found: {data_path}")
        return None

    df_1m = pd.read_csv(data_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m = df_1m.dropna(subset=['timestamp'])
    
    # Last 365 days
    cutoff = df_1m['timestamp'].max() - pd.Timedelta(days=365)
    df_1m = df_1m[df_1m['timestamp'] > cutoff].reset_index(drop=True)
    
    strategy = TrendCrusherV2(config=CONFIG)
    
    # Robust Parameters Injection
    kwargs = {
        'use_sniper': True,
        'retest_maker': False,
        'vol_mult': 2.2,
        'atr_trail_mult': 4.5,
        'ema_period': 100,
        'adx_threshold': 20,
        'donchian_period': 20,
        'risk_pct': risk_pct,
        'use_adaptive': True,
        'adaptive_steps': [
            {"pnl_pct": 5.0, "tighten_ratio": 0.5},
            {"pnl_pct": 8.0, "tighten_ratio": 0.3}
        ]
    }
    
    trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_1m, **kwargs)
    
    final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    mdd = np.max(drawdown) * 100
    
    print(f"✅ Result: Return {final_return:+.2f}% | MDD {mdd:.2f}% | Trades {len([t for t in trades if t['type']=='CLOSE'])}")
    
    # --- Save & Visualize ---
    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join("reports", clean_sym, f"Robust_Risk_{int(risk_pct*100)}", now_str)
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Visualization
    viz = TradingVisualizer()
    img_path = os.path.join(output_dir, f"report_{clean_sym}.png")
    temp_img = viz.generate_comprehensive_report(df_ind, trades, equity_curve, symbol, params=kwargs)
    if temp_img and os.path.exists(temp_img):
        os.rename(temp_img, img_path)
        print(f"🎨 Visual report: {img_path}")

    # 2. Summary
    with open(os.path.join(output_dir, "summary.txt"), "w") as f:
        f.write(f"Robust Simulation: {symbol} | Risk: {risk_pct*100}%\n")
        f.write(f"Return: {final_return:.2f}% | MDD: {mdd:.2f}%\n")
        f.write(f"Total Trades: {len(trades)}\n")
        f.write(f"Params: {kwargs}\n")
    
    return {"Symbol": symbol, "Risk": f"{risk_pct*100}%", "Return": final_return, "MDD": mdd}

async def main():
    symbols = ["ETH/USDT", "XRP/USDT", "XAU/USDT"]
    risks = [0.05, 0.08]
    results = []
    
    for sym in symbols:
        for r in risks:
            res = await run_robust_simulation(sym, r)
            if res: results.append(res)
    
    print("\n" + "="*50)
    print("FINAL ROBUSTNESS COMPARISON")
    print("="*50)
    df_res = pd.DataFrame(results)
    print(df_res.to_string(index=False))

if __name__ == "__main__":
    asyncio.run(main())
