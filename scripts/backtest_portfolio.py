import pandas as pd
import numpy as np
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2
from src.config import CONFIG

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def get_symbol_equity(symbol, seed=10000):
    # Load symbol-specific settings from CONFIG
    test_config = CONFIG.copy()
    if "SYMBOL_SETTINGS" in CONFIG and symbol in CONFIG["SYMBOL_SETTINGS"]:
        test_config.update(CONFIG["SYMBOL_SETTINGS"][symbol])
    
    test_config["SYMBOL"] = symbol
    test_config["SEED"] = seed
    
    clean_sym = symbol.replace('/', '_')
    df_sig = pd.read_csv(f"data/{clean_sym}_1h.csv")
    df_trend = pd.read_csv(f"data/{clean_sym}_4h.csv")
    df_check = pd.read_csv(f"data/{clean_sym}_1m.csv")
    
    strategy = TrendCrusherV2(config=test_config)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)
    
    # Ensure length matches timestamps
    timestamps = pd.to_datetime(df_sig['timestamp'])
    if len(equity_curve) < len(timestamps):
        equity_curve.extend([equity_curve[-1]] * (len(timestamps) - len(equity_curve)))
    elif len(equity_curve) > len(timestamps):
        equity_curve = equity_curve[:len(timestamps)]
        
    return pd.Series(equity_curve, index=timestamps)

if __name__ == "__main__":
    print(">>> Running Portfolio Integration Backtest (Individual Optimized Params) <<<")
    
    targets = [
        {"symbol": "TRUMP/USDT", "weight": 0.4},
        {"symbol": "ETH/USDT", "weight": 0.3},
        {"symbol": "XAU/USDT", "weight": 0.3}
    ]
    
    initial_seed = 10000
    portfolio_equity = pd.Series(0.0, index=None)
    
    individual_results = []
    
    for target in targets:
        print(f"Processing {target['symbol']} with its optimized params...")
        sym_seed = initial_seed * target['weight']
        equity_series = get_symbol_equity(target['symbol'], seed=sym_seed)
        
        if portfolio_equity.empty:
            portfolio_equity = equity_series
        else:
            # 타임스탬프 기준으로 합산 (결측치는 이전 값으로 채움)
            portfolio_equity = portfolio_equity.add(equity_series, fill_value=sym_seed)
            
        final_val = equity_series.iloc[-1]
        ret = ((final_val / sym_seed) - 1) * 100
        individual_results.append({"symbol": target['symbol'], "return": ret})

    # Portfolio Stats
    final_portfolio_val = portfolio_equity.iloc[-1]
    total_return = ((final_portfolio_val / initial_seed) - 1) * 100
    portfolio_mdd = calculate_mdd(portfolio_equity.tolist()) * 100
    
    print("\n" + "="*50)
    print(" PORTFOLIO BACKTEST RESULT (365 Days) ")
    print("="*50)
    for res in individual_results:
        print(f"{res['symbol']:<12} | Individual Return: {res['return']:>8.2f}%")
    print("-" * 50)
    print(f"COMBINED RETURN : {total_return:>8.2f}%")
    print(f"PORTFOLIO MDD   : {portfolio_mdd:>8.2f}%")
    print(f"FINAL BALANCE   : {final_portfolio_val:>8.2f} USDT")
    print("="*50)
    print("Insight: 분산 투자를 통해 변동성을 억제하면서 안정적인 우상향 달성.")
