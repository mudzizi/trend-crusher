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

def run_scenario(symbol, days, df_1m, params):
    # 2. Strategy Setup
    test_config = CONFIG.copy()
    v7_defaults = {
        "VOL_MULTIPLIER": 2.2,
        "RISK_PER_TRADE": params["risk_pct"],
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
    
    # Overwrite scenario parameters
    test_config["SYMBOL"] = symbol
    test_config["USE_SNIPER"] = params["use_sniper"]
    test_config["USE_RETEST_MAKER"] = False
    
    # Scalper Specific
    test_config["TAKE_PROFIT_ATR_MULT"] = params["tp_atr_mult"]
    test_config["TAKE_PROFIT_PCT"] = params["tp_pct"]
    test_config["BE_GUARD_THRESHOLD_SCALPER"] = params["be_guard"]
    test_config["INITIAL_SL_ATR"] = params["sl_atr"]
    test_config["TRAILING_ATR_MULT"] = params["trail_atr_mult"]
    
    strategy = TrendCrusherScalper(config=test_config)
    
    # Run Engine
    trades, equity_curve, _ = strategy.run_streaming_backtest(df_1m)
    
    if not trades:
        return None
        
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
        "Symbol": symbol,
        "Risk": f"{params['risk_pct']*100}%",
        "TP_ATR": params["tp_atr_mult"],
        "SL_ATR": params["sl_atr"],
        "Trail_ATR": params["trail_atr_mult"],
        "BE_Guard": f"{params['be_guard']}%",
        "Sniper": params["use_sniper"],
        "Return": round(ret, 2),
        "MDD": round(mdd, 2),
        "Trades": len(processed_trades),
        "WinRate": round(win_rate, 2),
        "Eff": round(eff, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="TrendCrusher Scalper Scenario Tester")
    parser.add_argument("--symbols", type=str, default="ETH/USDT,XRP/USDT,TRUMP/USDT", help="Comma-separated symbols")
    parser.add_argument("--days", type=int, default=30, help="Days to backtest")
    args = parser.parse_args()
    
    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    
    # Sync Data First
    fetcher = BinanceDataFetcher()
    for symbol in symbols:
        print(f"🔄 Syncing data for {symbol}...")
        for tf in ["1h", "4h", "1m"]:
            try:
                fetcher.save_all(symbol=symbol, days=args.days + 10)
                break
            except Exception as e:
                pass
                
    # Define Parameter Grid
    # Short duration & Quick exits
    scenarios = []
    
    # Combinations to test
    risk_pcts = [0.01, 0.02]
    tp_atr_mults = [1.0, 1.5, 2.0]
    sl_atrs = [1.0, 1.5, 2.0]
    trail_atrs = [2.0, 3.5, 5.0]
    be_guards = [0.5, 1.0]
    use_snipers = [True, False]
    
    # We will generate a smart grid subset to avoid exploding trials, target ~24 representative combinations
    grid = []
    for r in risk_pcts:
        for sniper in use_snipers:
            for tp in tp_atr_mults:
                for sl in sl_atrs:
                    # Keep SL ATR and TP ATR closer or reasonable (e.g. don't do TP=1.0 and SL=2.0 usually)
                    if sl > tp + 0.5:
                        continue
                    for trail in [3.5]: # lock trailing ATR to avoid too many trials
                        for be in [1.0]: # lock BE guard to 1.0%
                            grid.append({
                                "risk_pct": r,
                                "use_sniper": sniper,
                                "tp_atr_mult": tp,
                                "tp_pct": 0.0,
                                "sl_atr": sl,
                                "trail_atr_mult": trail,
                                "be_guard": be
                            })
                            
    print(f"Generated {len(grid)} parameter combinations for testing.")
    
    for symbol in symbols:
        clean_sym = symbol.replace('/', '_')
        data_path = f"data/{clean_sym}_1m.csv"
        if not os.path.exists(data_path):
            print(f"❌ Data file {data_path} not found for {symbol}. Skipping.")
            continue
            
        df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
        cutoff = datetime.now() - timedelta(days=args.days)
        df_1m = df_1m[df_1m['timestamp'] >= cutoff].copy()
        
        if df_1m.empty:
            print(f"❌ No data for {symbol} in the requested period. Skipping.")
            continue
            
        print(f"\n📊 Running scenarios for {symbol} ({len(df_1m)} mins of data)...")
        results = []
        
        for idx, params in enumerate(grid):
            try:
                res = run_scenario(symbol, args.days, df_1m, params)
                if res:
                    results.append(res)
            except Exception as e:
                print(f"Error running scenario {idx}: {e}")
                
        if results:
            res_df = pd.DataFrame(results)
            # Sort by Efficiency descending, then Return descending
            res_df = res_df.sort_values(by=["Eff", "Return"], ascending=[False, False])
            
            # Print top 5
            print(f"\n🏆 TOP 5 SCENARIOS FOR {symbol}:")
            print(res_df.head(5).to_string(index=False))
            
            # Save all
            os.makedirs("reports/scalper", exist_ok=True)
            out_path = f"reports/scalper/{clean_sym}_scenarios.csv"
            res_df.to_csv(out_path, index=False)
            print(f"💾 Saved all results to {out_path}")
        else:
            print(f"⚠️ No trades executed in any scenarios for {symbol}.")

if __name__ == "__main__":
    main()
