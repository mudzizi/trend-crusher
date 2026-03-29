import pandas as pd
import numpy as np
import os
import time
import csv
from datetime import datetime, timedelta
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG

# --- [INPUT CONFIGURATION] ---
SUMMARY_FILE = "reports/optuna_optimization/run_20260329_2109/optuna_summary.csv"
QUARTERS_TO_TEST = 4
# ----------------------------

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_single_test(data_1m, ind_cache, params, strategy, quarter_start_date):
    vol = float(params['Vol'])
    trail = float(params['Trail'])
    adx_val = float(params['ADX'])
    don = int(params['Don'])
    ep = int(params['EMA'])
    risk = 0.02 # FIXED for fair robustness test
    
    mode = params['Mode']
    sniper = (mode == "Sniper")
    retest = (mode == "Retest")
    
    adapt_type = params['Adapt']
    adapt = []
    if adapt_type == "Tight":
        adapt = [{"pnl_pct": 2.0, "tighten_ratio": 0.5}]
    elif adapt_type == "Aggressive":
        adapt = [{"pnl_pct": 5.0, "tighten_ratio": 0.7}]

    trades, equity_curve, _ = strategy.run_streaming_backtest(
        data_1m,
        vol_mult=vol, atr_trail_mult=trail, risk_pct=risk,
        adx_threshold=adx_val, donchian_period=don,
        ema_period=ep,
        use_sniper=sniper, retest_maker=retest,
        use_adaptive=(adapt_type != "None"), adaptive_steps=adapt,
        pre_calculated_ind=ind_cache[(don, ep)]
    )
    
    # DEBUG: Check first trade and quarter_start_date
    if trades:
        print(f"DEBUG: First trade time: {trades[0]['time']} (Type: {type(trades[0]['time'])})")
        print(f"DEBUG: Quarter Start: {quarter_start_date} (Type: {type(quarter_start_date)})")

    # Filter trades to only those that opened AFTER the intended quarter started
    q_trades = [t for t in trades if pd.Timestamp(t['time']) >= pd.Timestamp(quarter_start_date) and t['type'] == 'CLOSE']
    
    # Calculate return ONLY for these trades
    capital = CONFIG["SEED"]
    for t in q_trades:
        capital += t['pnl_usdt']
    
    ret = ((capital / CONFIG["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    return ret, mdd, len(q_trades)

def main():
    if not os.path.exists(SUMMARY_FILE):
        print(f"Error: {SUMMARY_FILE} not found.")
        return

    df_summary = pd.read_csv(SUMMARY_FILE)
    symbols = df_summary['Symbol'].unique()
    
    strategy = TrendCrusherV2(config=CONFIG)
    robustness_results = []

    for sym in symbols:
        print(f"\n{'='*20} TESTING ROBUSTNESS: {sym} {'='*20}")
        data_path = f"data/{sym}_1m.csv"
        if not os.path.exists(data_path): continue
        df_1m_all = pd.read_csv(data_path, parse_dates=['timestamp'])
        latest_date = df_1m_all['timestamp'].max()

        # 1. Prepare Quarter Data & Ind Caches (Chronological: Q1 = earliest)
        q_data = {}
        # Get start of all data
        earliest_date = df_1m_all['timestamp'].min()
        
        for q in range(1, QUARTERS_TO_TEST + 1):
            start_date = earliest_date + timedelta(days=(q-1)*90)
            end_date = start_date + timedelta(days=90)
            # Add 30 days of data BEFORE for warmup
            warmup_start = start_date - timedelta(days=30)
            
            data_q_full = df_1m_all[(df_1m_all['timestamp'] >= warmup_start) & (df_1m_all['timestamp'] < end_date)].copy()
            if len(data_q_full) < 1440 * 10: continue
            
            # Pre-calc Indicators for this full (warmup + quarter) data
            df_1h_base = get_all_base_bars(data_q_full, "1h")
            df_4h_base = get_all_base_bars(data_q_full, "4h")
            
            don_periods = [10, 20, 30]
            ema_periods = [50, 100, 200]
            ema_cache = {}
            for ep in ema_periods:
                actual_ep = ep if len(df_4h_base) >= ep else max(10, len(df_4h_base)//2)
                ema_v = calculate_ema(df_4h_base, actual_ep)
                ema_s = pd.Series(ema_v.values, index=df_4h_base['timestamp'])
                ema_cache[ep] = ema_s.reindex(df_1h_base['timestamp']).ffill().values
            
            atr = calculate_atr(df_1h_base, 14)
            avg_vol = calculate_avg_vol(df_1h_base, 20)
            adx = calculate_adx(df_1h_base, 14)
            
            ind_cache = {}
            for dp in don_periods:
                for ep in ema_periods:
                    df_ind = df_1h_base.copy()
                    df_ind['upper'], df_ind['lower'] = calculate_donchian(df_ind, dp)
                    df_ind['ema_h'], df_ind['atr'], df_ind['avg_vol'], df_ind['adx'] = ema_cache[ep], atr, avg_vol, adx
                    ind_cache[(dp, ep)] = df_ind.dropna(subset=['upper', 'lower', 'atr', 'avg_vol', 'adx'])
            
            q_data[f"Q{q}"] = (data_q_full, ind_cache, start_date)

        # 2. Cross-Test Parameter Sets
        sym_best_params = df_summary[df_summary['Symbol'] == sym]
        
        for idx, row in sym_best_params.iterrows():
            param_q_name = row['Quarter']
            print(f"   - Testing Params Optimized for {param_q_name} against all quarters...")
            
            for test_q_name, (data_q_full, ind_cache, q_start_date) in q_data.items():
                ret, mdd, trades = run_single_test(data_q_full, ind_cache, row, strategy, q_start_date)
                
                robustness_results.append({
                    "Symbol": sym,
                    "Param_Source": param_q_name,
                    "Test_Quarter": test_q_name,
                    "Return": round(ret, 2),
                    "MDD": round(mdd, 2),
                    "Trades": trades,
                    "Is_In_Sample": (param_q_name == test_q_name)
                })

    # 3. Save & Report
    res_df = pd.DataFrame(robustness_results)
    output_path = "reports/optuna_optimization/run_20260329_1706/robustness_matrix.csv"
    res_df.to_csv(output_path, index=False)
    
    print(f"\n{'='*60}")
    print(f"ROBUSTNESS TEST COMPLETE! Results in: {output_path}")
    print(f"{'='*60}")
    
    # Ranking
    print("\n[ Robustness Ranking (Avg Return across ALL quarters) ]")
    summary = res_df.groupby(['Symbol', 'Param_Source'])['Return'].mean().reset_index()
    summary = summary.sort_values(by=['Symbol', 'Return'], ascending=[True, False])
    print(summary)

    # Ranking (Out-of-Sample only)
    print("\n[ Robustness Ranking (Avg Return across Out-of-Sample ONLY) ]")
    summary_oos = res_df[res_df['Is_In_Sample'] == False].groupby(['Symbol', 'Param_Source'])['Return'].mean().reset_index()
    summary_oos = summary_oos.sort_values(by=['Symbol', 'Return'], ascending=[True, False])
    print(summary_oos)

if __name__ == "__main__":
    main()
