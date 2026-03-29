import pandas as pd
import numpy as np
import asyncio
import os
from datetime import datetime
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.visualizer import TradingVisualizer

async def run_2024_robust_simulation(symbol, risk_pct):
    clean_sym = symbol.replace('/', '_')
    print(f"\n🚀 [2024 FULL YEAR] {symbol} | RISK: {risk_pct*100}%")
    
    # Load 2024 specific data
    data_path = f"data/{clean_sym}_2024_1m.csv"
    if not os.path.exists(data_path):
        print(f"⚠️ Data not found: {data_path}")
        return None

    df_1m = pd.read_csv(data_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    
    strategy = TrendCrusherV2(config=CONFIG)
    
    # Robust Parameters
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
    
    print(f"✅ 2024 Result: Return {final_return:+.2f}% | MDD {mdd:.2f}% | Trades {len([t for t in trades if t['type']=='CLOSE'])}")
    
    # Save & Visualize
    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join("reports", clean_sym, "2024_FULL", f"Risk_{int(risk_pct*100)}", now_str)
    os.makedirs(output_dir, exist_ok=True)
    
    # 0. Save Trades CSV
    pd.DataFrame(trades).to_csv(os.path.join(output_dir, "trades.csv"), index=False)
    
    viz = TradingVisualizer()
    img_path = os.path.join(output_dir, f"report_2024_{clean_sym}.png")
    temp_img = viz.generate_comprehensive_report(df_ind, trades, equity_curve, symbol, params=kwargs)
    if temp_img and os.path.exists(temp_img):
        os.rename(temp_img, img_path)
    
    return {"Symbol": symbol, "Risk": f"{risk_pct*100}%", "Return": final_return, "MDD": mdd}

async def main():
    symbols = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"]
    risks = [0.05, 0.08]
    results = []
    
    for sym in symbols:
        for r in risks:
            res = await run_2024_robust_simulation(sym, r)
            if res: results.append(res)
    
    print("\n" + "="*50)
    print("FINAL 2024 ROBUSTNESS SUMMARY")
    print("="*50)
    df_res = pd.DataFrame(results)
    print(df_res.to_string(index=False))

if __name__ == "__main__":
    asyncio.run(main())
