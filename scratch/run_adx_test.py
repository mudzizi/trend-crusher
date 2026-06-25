import os
import sys
sys.path.append(os.getcwd())

from scripts.backtest import run_backtest

# Lower ADX filters to 5.0 so they have almost zero filtering effect
overrides = {
    "ADX_FILTER_LEVEL": 5.0,
    "ADX_4H_THRESHOLD": 5.0
}

print("=== XRP/USDT (Low ADX) ===")
run_backtest("XRP/USDT", 90, "market", strategy_name="v2", risk_pct=0.08, config_overrides=overrides)

print("\n=== SUI/USDT (Low ADX) ===")
run_backtest("SUI/USDT", 90, "market", strategy_name="v2", risk_pct=0.08, config_overrides=overrides)

print("\n=== TRUMP/USDT (Low ADX) ===")
run_backtest("TRUMP/USDT", 90, "market", strategy_name="v2", risk_pct=0.08, config_overrides=overrides)
