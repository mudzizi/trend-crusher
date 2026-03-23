import pandas as pd
import numpy as np
import os
import itertools
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor
from src.strategy import TrendCrusherV2
from src.config import CONFIG

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def worker_task(task_args):
    data_1m, combo = task_args
    vol, trail, risk, mode_info = combo
    m_name, sniper, retest = mode_info
    
    strategy = TrendCrusherV2(config=CONFIG)
    # Testing the fixed 3-value return
    trades, equity_curve, _ = strategy.run_streaming_backtest(
        data_1m,
        vol_mult=vol,
        atr_trail_mult=trail,
        risk_pct=risk,
        use_sniper=sniper,
        retest_maker=retest
    )
    
    if len(trades) >= 1:
        ret = ((strategy.capital / CONFIG["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        return {"Return": ret, "MDD": mdd, "Mode": m_name}
    return None

def main():
    sym = "ETH_USDT"
    print(f"🛠️ Starting Quick Test for {sym}...")
    
    df_1m = pd.read_csv(f"data/{sym}_1m.csv", parse_dates=['timestamp'])
    latest_date = df_1m['timestamp'].max()
    start_date = latest_date - timedelta(days=30)
    data_1m_test = df_1m[df_1m['timestamp'] >= start_date].copy()

    # Tiny Grid for testing
    vols = [2.0]
    trails = [3.0]
    risks = [0.05]
    modes = [('Market', False, False), ('Sniper', True, False)]
    
    combinations = list(itertools.product(vols, trails, risks, modes))
    tasks = [(data_1m_test, combo) for combo in combinations]
    
    print(f"Testing {len(tasks)} combos with ProcessPoolExecutor...")
    with ProcessPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker_task, tasks))
    
    valid = [r for r in results if r]
    print(f"✅ Test Complete. Valid results: {len(valid)}/{len(tasks)}")
    for r in valid:
        print(f"   - {r['Mode']}: Return {r['Return']:.2f}% | MDD {r['MDD']:.2f}%")

if __name__ == "__main__":
    main()
