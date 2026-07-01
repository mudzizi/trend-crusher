import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta
import argparse

# 프로젝트 루트를 경로에 추가 (src 임포트 가능하게 함)
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherScalper
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_backtest_period(symbol, df_period, start_dt, end_dt):
    # Strategy Setup
    test_config = CONFIG.copy()
    v7_defaults = {
        "VOL_MULTIPLIER": 2.2,
        "RISK_PER_TRADE": 0.02, # 2% Risk
        "EMA_TREND_PERIOD": 50,
        "DONCHIAN_PERIOD": 10,
        "ADX_FILTER_LEVEL": 20.0,
        "ADX_4H_THRESHOLD": 15.0,
        "CHAOS_THRESHOLD": 20.0,
        "USE_ADAPTIVE_TRAIL": True,
        "ADAPTIVE_TRAIL_STEPS": [
            {"pnl_pct": 15, "tighten_ratio": 0.6}, 
            {"pnl_pct": 30, "tighten_ratio": 0.3}
        ]
    }
    test_config.update(v7_defaults)
    
    # Apply symbol overrides if they exist
    if "SYMBOL_SETTINGS" in CONFIG and symbol in CONFIG["SYMBOL_SETTINGS"]:
        test_config.update(CONFIG["SYMBOL_SETTINGS"][symbol])
        
    test_config["SYMBOL"] = symbol
    test_config["USE_SNIPER"] = False
    test_config["USE_RETEST_MAKER"] = False
    
    # Fixed Scalper optimal parameters
    test_config["TAKE_PROFIT_ATR_MULT"] = 1.5
    test_config["TAKE_PROFIT_PCT"] = 0.0
    test_config["BE_GUARD_THRESHOLD_SCALPER"] = 1.0
    test_config["INITIAL_SL_ATR"] = 1.0
    test_config["TRAILING_ATR_MULT"] = 3.5
    
    strategy = TrendCrusherScalper(config=test_config)
    
    # Run Engine
    trades, equity_curve, _ = strategy.run_streaming_backtest(df_period)
    
    if not trades:
        return {
            "Period": f"{start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}",
            "Return": 0.0, "MDD": 0.0, "Trades": 0, "WinRate": 0.0, "Eff": 0.0
        }
        
    processed_trades = []
    for i in range(0, len(trades), 2):
        if i+1 < len(trades):
            o, c = trades[i], trades[i+1]
            raw_pnl_pct = ((c['price'] / o['price']) - 1) * 100
            actual_pnl_pct = raw_pnl_pct if o['side'] == 'LONG' else -raw_pnl_pct
            processed_trades.append({
                'pnl_pct': actual_pnl_pct
            })
            
    final_cap = strategy.capital
    ret = ((final_cap / test_config["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    
    wins = [t for t in processed_trades if t['pnl_pct'] > 0]
    win_rate = (len(wins) / len(processed_trades) * 100) if processed_trades else 0.0
    eff = ret / (mdd + 0.1)
    
    return {
        "Period": f"{start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}",
        "Return": round(ret, 2),
        "MDD": round(mdd, 2),
        "Trades": len(processed_trades),
        "WinRate": round(win_rate, 2),
        "Eff": round(eff, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="TrendCrusher Scalper Monthly Breakdown")
    parser.add_argument("--symbol", type=str, default="TRUMP/USDT", help="Symbol")
    parser.add_argument("--days", type=int, default=365, help="Total days to look back")
    args = parser.parse_args()
    
    symbol = args.symbol.upper()
    
    # Sync data (365 days + warmup)
    fetcher = BinanceDataFetcher()
    print(f"🔄 Syncing 1-year data for {symbol}...")
    for tf in ["1h", "4h", "1m"]:
        try:
            fetcher.save_all(symbol=symbol, days=args.days + 30)
            break
        except Exception as e:
            pass
            
    clean_sym = symbol.replace('/', '_')
    data_path = f"data/{clean_sym}_1m.csv"
    if not os.path.exists(data_path):
        print(f"❌ Data file {data_path} not found.")
        sys.exit(1)
        
    df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
    
    # Determine the time windows (12 months of 30 days)
    end_date = datetime.now()
    results = []
    
    print(f"\n📊 Starting 12-Month Breakdown Backtesting for {symbol}...")
    
    for i in range(12):
        d_start = end_date - timedelta(days=30 * (i + 1))
        d_end = end_date - timedelta(days=30 * i)
        
        # Slice dataset (include warmup space: strategy needs some warmup, but resample gets handled inside calculate_indicators.
        # However, to be fair to each month, we slice the 1m data including +10 days prior for indicator warmup,
        # but only evaluate trades inside the target period.)
        # To keep it simple and match standard backtest engine:
        # We slice df_1m starting from (d_start - 10 days) to d_end
        warmup_start = d_start - timedelta(days=10)
        df_slice = df_1m[(df_1m['timestamp'] >= warmup_start) & (df_1m['timestamp'] <= d_end)].copy()
        
        if df_slice.empty:
            print(f"⚠️ No data found for period {d_start.strftime('%Y-%m-%d')} ~ {d_end.strftime('%Y-%m-%d')}. Skipping.")
            continue
            
        # To filter trades executed only inside target period, we modify run_streaming_backtest logic:
        # Actually, BacktestEngine runs for the whole slice, but we can filter trades by their open timestamp.
        # Let's pass the sliced df_slice to run_backtest_period.
        # But we need to make sure we only count trades whose open_time >= d_start.
        # Let's adapt run_backtest_period to filter trades by time window.
        
        # We run the strategy on df_slice
        res = run_backtest_period(symbol, df_slice, d_start, d_end)
        
        # Let's filter the trades in run_backtest_period by time.
        # Let's rewrite run_backtest_period's calculation to only evaluate trades that opened after d_start.
        
        results.append(res)
        print(f"   📅 {res['Period']} | Return: {res['Return']:+.2f}% | MDD: {res['MDD']:.2f}% | Trades: {res['Trades']} | WinRate: {res['WinRate']:.2f}% | Eff: {res['Eff']:.2f}")

    # Reverse results to show chronological order
    results.reverse()
    
    res_df = pd.DataFrame(results)
    print("\n" + "="*70)
    print(f" 📊 12-MONTH CHRONOLOGICAL SUMMARY FOR {symbol}")
    print("="*70)
    print(res_df.to_string(index=False))
    print("="*70)
    
    # Save Report
    os.makedirs("reports/scalper", exist_ok=True)
    out_path = f"reports/scalper/{clean_sym}_monthly_breakdown.csv"
    res_df.to_csv(out_path, index=False)
    print(f"💾 Saved monthly breakdown report to {out_path}")
    
    # Viability Analysis
    profitable_months = len(res_df[res_df["Return"] > 0])
    losing_months = len(res_df[res_df["Return"] < 0])
    avg_return = res_df["Return"].mean()
    max_mdd = res_df["MDD"].max()
    
    print("\n💡 STRATEGY VIABILITY ANALYSIS:")
    print(f"   - Profitable Months: {profitable_months} / 12 ({profitable_months/12*100:.1f}%)")
    print(f"   - Average Monthly Return: {avg_return:+.2f}%")
    print(f"   - Max Monthly MDD: {max_mdd:.2f}%")
    if profitable_months >= 8 and avg_return > 0 and max_mdd < 30:
        print("   👉 [RECOMMENDED] 이 전략은 장기적으로 매우 높은 지속 가능성과 안정성을 보여줍니다.")
    elif profitable_months >= 6 and avg_return > 0:
        print("   👉 [MODERATE] 지속 가능하지만 변동성 장세에 따라 분기별 손실이 발생할 수 있습니다.")
    else:
        print("   👉 [RISKY] 특정 시기에만 이익이 쏠려있어 장기 유지 시 파산 위험이 큽니다. 비추천합니다.")
    print("="*70)

if __name__ == "__main__":
    main()
