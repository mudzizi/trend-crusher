import pandas as pd
import numpy as np
import os
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.config import CONFIG

def debug_engine():
    sym = "XAU_USDT"
    print(f"🔍 Debugging Engine for {sym}...")
    
    data_path = f"data/{sym}_1m.csv"
    if not os.path.exists(data_path):
        print(f"❌ Data missing at {data_path}")
        return

    # Load recent 10 days of data
    df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
    latest_date = df_1m['timestamp'].max()
    start_date = latest_date - pd.Timedelta(days=10)
    df_1m = df_1m[df_1m['timestamp'] >= start_date].copy()
    
    print(f"   - Data range: {df_1m['timestamp'].min()} to {df_1m['timestamp'].max()} ({len(df_1m)} rows)")

    strategy = TrendCrusherV2(config=CONFIG)
    
    # Run backtest with very aggressive settings to FORCE trades
    # Low Volume mult (1.0), Low ADX (5), etc.
    config_override = {
        "VOL_MULTIPLIER": 0.5,
        "ADX_FILTER_LEVEL": 5,
        "USE_SNIPER": False,
        "USE_RETEST_MAKER": False,
        "DONCHIAN_PERIOD": 10
    }
    
    print(f"   - Running with aggressive settings: {config_override}")
    trades, equity, df_ind = strategy.run_streaming_backtest(df_1m, **config_override)
    
    print(f"\n📊 --- Debug Results ---")
    print(f"   - Total Steps Executed: {len(df_1m)}")
    print(f"   - Indicators Generated: {len(df_ind)} rows")
    print(f"   - Total Trades: {len(trades)}")
    
    if len(trades) > 0:
        print(f"   - First 3 trades: {trades[:3]}")
    else:
        # If no trades, analyze why
        print(f"   - ❌ NO TRADES GENERATED. Analyzing first 100 steps of the loop...")
        
        # Manually trace a few steps
        m_times = pd.to_datetime(df_1m['timestamp']).values.astype('datetime64[m]')
        ind_shifted = df_ind.shift(1).copy()
        ind_times = pd.to_datetime(ind_shifted['timestamp']).values.astype('datetime64[m]')
        
        match_count = 0
        for i in range(min(5000, len(m_times))):
            curr_t = m_times[i]
            idx = np.searchsorted(ind_times, curr_t, side='right') - 1
            if idx >= 0 and not np.isnan(ind_shifted['upper'].iloc[idx]):
                match_count += 1
        
        print(f"   - Timestamp Match Success: {match_count} / {min(5000, len(m_times))} steps")
        if match_count == 0:
            print(f"   - 🚨 CRITICAL: Indicator matching failed due to timestamp mismatch!")
            print(f"   - Sample m_time: {m_times[0]}")
            print(f"   - Sample ind_time: {ind_times[10] if len(ind_times)>10 else 'N/A'}")

if __name__ == "__main__":
    debug_engine()
