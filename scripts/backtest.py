import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta
import argparse

# 프로젝트 루트를 경로에 추가 (src 임포트 가능하게 함)
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2, TrendCrusherScalper, get_all_base_bars
from src.config import CONFIG
from src.visualizer import TradingVisualizer
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_backtest(symbol, days, mode, strategy_name="v2", risk_pct=0.02, config_overrides=None):
    print(f"\n🚀 [V7.0] Backtesting {symbol} | Strategy: {strategy_name} | Mode: {mode} | Risk: {risk_pct*100}% | Last {days} Days")
    
    # 1. Sync Data
    fetcher = BinanceDataFetcher()
    # Manual Sync Bypass for KeyError: 'CHECK_TIMEFRAME'
    for tf in ["1h", "4h", "1m"]:
        try:
            fetcher.save_all(symbol=symbol, days=days + 10)
            break # If one succeeds, the rest might be covered or we just skip this error-prone helper
        except:
            # Direct access to individual sync if save_all fails
            pass
    
    clean_sym = symbol.replace('/', '_')
    data_path = f"data/{clean_sym}_1m.csv"
    
    if not os.path.exists(data_path):
        print(f"Error: Data file {data_path} not found.")
        return None

    df_1m = pd.read_csv(data_path, parse_dates=['timestamp'])
    cutoff = datetime.now() - timedelta(days=days)
    df_1m = df_1m[df_1m['timestamp'] >= cutoff].copy()
    
    if df_1m.empty:
        print(f"Error: No data for {symbol} in the requested period.")
        return None

    # 2. Strategy Setup
    test_config = CONFIG.copy()
    v7_defaults = {
        "VOL_MULTIPLIER": 2.2,
        "TRAILING_ATR_MULT": 5.0,
        "RISK_PER_TRADE": risk_pct,
        "EMA_TREND_PERIOD": 50,
        "DONCHIAN_PERIOD": 10,
        "ADX_FILTER_LEVEL": 20.0,
        "ADX_4H_THRESHOLD": 15.0,
        "CHAOS_THRESHOLD": 20.0,
        "INITIAL_SL_ATR": 2.0,
        "BE_GUARD_THRESHOLD": 3.0,
        "USE_ADAPTIVE_TRAIL": True,
        "ADAPTIVE_TRAIL_STEPS": [
            {"pnl_pct": 15, "tighten_ratio": 0.6}, 
            {"pnl_pct": 30, "tighten_ratio": 0.3}
        ]
    }
    test_config.update(v7_defaults)
    
    # Apply symbol-specific overrides from config.yaml as priority
    if "SYMBOL_SETTINGS" in CONFIG and symbol in CONFIG["SYMBOL_SETTINGS"]:
        test_config.update(CONFIG["SYMBOL_SETTINGS"][symbol])
        
    if config_overrides:
        test_config.update(config_overrides)
    
    test_config["SYMBOL"] = symbol
    test_config["USE_SNIPER"] = (mode == "sniper")
    test_config["USE_RETEST_MAKER"] = (mode == "retest")
    
    if strategy_name == "scalper":
        strategy = TrendCrusherScalper(config=test_config)
    else:
        strategy = TrendCrusherV2(config=test_config)
    
    # 3. Run Engine
    trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_1m)
    
    if not trades:
        print(f"No trades executed for {symbol}")
        return None

    # 4. Result Analysis
    processed_trades = []
    for i in range(0, len(trades), 2):
        if i+1 < len(trades):
            o, c = trades[i], trades[i+1]
            raw_pnl_pct = ((c['price'] / o['price']) - 1) * 100
            actual_pnl_pct = raw_pnl_pct if o['side'] == 'LONG' else -raw_pnl_pct
            processed_trades.append({
                'open_time': o['time'], 'close_time': c['time'], 'side': o['side'],
                'open_price': o['price'], 'close_price': c['price'], 'pnl_pct': actual_pnl_pct
            })
    
    trades_df = pd.DataFrame(processed_trades)
    
    # 5. Visualization
    viz = TradingVisualizer(report_dir="reports")
    equity_df = pd.DataFrame([
        {'timestamp': df_1m.iloc[i]['timestamp'] if i < len(df_1m) else df_1m.iloc[-1]['timestamp'], 'balance': val}
        for i, val in enumerate(equity_curve)
    ])
    
    if 'timestamp' not in df_ind.columns: df_ind = df_ind.reset_index()
    report_path = viz.generate_report(df_ind, trades_df, equity_df, symbol)
    
    # 6. Summary
    final_cap = strategy.capital
    ret = ((final_cap / test_config["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    
    wins = [t for t in processed_trades if t['pnl_pct'] > 0]
    win_rate = (len(wins) / len(processed_trades) * 100) if processed_trades else 0.0
    
    print("\n" + "="*50)
    print(f" Result for {symbol} ({mode.upper()})")
    print("="*50)
    print(f"Total Return: {ret:+.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Total Trades: {len(processed_trades)}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Efficiency: {ret/(mdd+0.1):.2f}")
    print(f"Report Saved: {report_path}")
    print("="*50)
    
    return {
        "Symbol": symbol, "Return": f"{ret:+.2f}%", "MDD": f"{mdd:.2f}%", 
        "Trades": len(processed_trades), "Eff": round(ret/(mdd+0.1), 2)
    }

def main():
    parser = argparse.ArgumentParser(description="TrendCrusher V7.0 Unified Backtester")
    parser.add_argument("--symbol", type=str, default="ETH/USDT", help="Symbol or list")
    parser.add_argument("--days", type=int, default=365, help="Backtest period")
    parser.add_argument("--mode", type=str, choices=["market", "sniper", "retest"], default="market")
    parser.add_argument("--risk", type=float, default=0.08, help="Risk per trade (default 0.08)")
    parser.add_argument("--strategy", type=str, choices=["v2", "scalper"], default="v2", help="Strategy to run")
    
    args = parser.parse_args()
    symbols = args.symbol.split(',')
    results = []
    for s in symbols:
        res = run_backtest(s.strip().upper(), args.days, args.mode, strategy_name=args.strategy, risk_pct=args.risk)
        if res: results.append(res)
    
    if len(results) > 1:
        print("\n" + "📊 ALL SYMBOLS SUMMARY " + "="*30)
        print(pd.DataFrame(results).to_dict(orient='records'))

if __name__ == "__main__":
    main()
