import sys
import os
import pandas as pd

# Add project root to sys.path
sys.path.append(os.getcwd())

from scripts.backtest import run_backtest

def run_suite(risk_pct):
    symbol = "SUI/USDT"
    days = 180
    mode = "market"
    
    print(f"\n=================== RUNNING SUITE WITH RISK {risk_pct*100}% ===================")
    baseline_res = run_backtest(
        symbol=symbol, 
        days=days, 
        mode=mode, 
        risk_pct=risk_pct, 
        config_overrides=None
    )
    
    moderate_res = run_backtest(
        symbol=symbol, 
        days=days, 
        mode=mode, 
        risk_pct=risk_pct, 
        config_overrides={
            "ADX_FILTER_LEVEL": 25.0,
            "VOL_MULTIPLIER": 2.2
        }
    )
    
    aggressive_res = run_backtest(
        symbol=symbol, 
        days=days, 
        mode=mode, 
        risk_pct=risk_pct, 
        config_overrides={
            "ADX_FILTER_LEVEL": 20.0,
            "VOL_MULTIPLIER": 1.8
        }
    )
    
    return baseline_res, moderate_res, aggressive_res

def main():
    # Run with 10% Risk (Current SUI Config)
    r10_base, r10_mod, r10_agg = run_suite(0.10)
    
    # Run with 3% Risk (Standard Money Management)
    r3_base, r3_mod, r3_agg = run_suite(0.03)
    
    print("\n" + "="*90)
    print(" COMPARISON RESULTS (180 Days, SUI/USDT) - RISK: 10% vs 3%")
    print("="*90)
    print(f"{'Metric':<12} | {'[Risk 10%] Base':<16} | {'[Risk 10%] Mod':<16} | {'[Risk 3%] Base':<16} | {'[Risk 3%] Mod':<16}")
    print("-"*90)
    
    def get_val(res, key):
        return res[key] if res else "N/A"
        
    print(f"{'Return':<12} | {get_val(r10_base, 'Return'):<16} | {get_val(r10_mod, 'Return'):<16} | {get_val(r3_base, 'Return'):<16} | {get_val(r3_mod, 'Return'):<16}")
    print(f"{'Max Drawdown':<12} | {get_val(r10_base, 'MDD'):<16} | {get_val(r10_mod, 'MDD'):<16} | {get_val(r3_base, 'MDD'):<16} | {get_val(r3_mod, 'MDD'):<16}")
    print(f"{'Trades':<12} | {get_val(r10_base, 'Trades'):<16} | {get_val(r10_mod, 'Trades'):<16} | {get_val(r3_base, 'Trades'):<16} | {get_val(r3_mod, 'Trades'):<16}")
    print(f"{'Efficiency':<12} | {get_val(r10_base, 'Eff'):<16} | {get_val(r10_mod, 'Eff'):<16} | {get_val(r3_base, 'Eff'):<16} | {get_val(r3_mod, 'Eff'):<16}")
    print("="*90)

if __name__ == "__main__":
    main()
