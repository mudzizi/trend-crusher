import ccxt
import pandas as pd
import numpy as np
import os
import itertools
import time
from datetime import datetime, timedelta
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def get_top_20_usdt_m():
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    tickers = exchange.fetch_tickers()
    usdt_m_tickers = {symbol: data for symbol, data in tickers.items() if '/USDT' in symbol}
    sorted_tickers = sorted(usdt_m_tickers.items(), key=lambda x: x[1]['quoteVolume'] if 'quoteVolume' in x[1] else 0, reverse=True)
    return [symbol for symbol, _ in sorted_tickers[:20]]

def mega_optimization(limit=20):
    symbols = get_top_20_usdt_m()[:limit]
    print(f"Top {len(symbols)} Symbols: {symbols}")

    vol_multipliers = [1.5, 2.0, 2.5]
    trailing_mults = [3.0, 3.5, 4.0, 4.5]
    ema_periods = [100, 200]
    risk = 0.02

    results = []
    
    os.makedirs(CONFIG["DATA_DIR"], exist_ok=True)
    
    fetcher = BinanceDataFetcher()

    for sym in symbols:
        print(f"\nProcessing {sym}...")
        clean_sym = sym.replace('/', '_').replace(':', '_')
        
        # Fetch Data
        timeframes = ["1h", "4h", "1m"]
        data = {}
        for tf in timeframes:
            filename = f"{CONFIG['DATA_DIR']}/{clean_sym}_{tf}.csv"
            if os.path.exists(filename):
                # Check if it's recent enough (let's say less than 24h old)
                mtime = os.path.getmtime(filename)
                if time.time() - mtime < 86400: # 1 day
                    print(f"Loading existing data for {sym} {tf}")
                    data[tf] = pd.read_csv(filename)
                    continue
            
            # Fetch if not exists or old
            df = fetcher.fetch_ohlcv(sym, tf, 365)
            df.to_csv(filename, index=False)
            data[tf] = df
            print(f"Saved {tf} data for {sym}")

        # Optimization Grid
        combinations = list(itertools.product(vol_multipliers, trailing_mults, ema_periods))
        
        for vol, trail, ema in combinations:
            current_config = CONFIG.copy()
            current_config.update({
                "SYMBOL": sym,
                "VOL_MULTIPLIER": vol,
                "TRAILING_ATR_MULT": trail,
                "RISK_PER_TRADE": risk,
                "EMA_TREND_PERIOD": ema
            })

            strategy = TrendCrusherV2(config=current_config)
            trades, equity_curve = strategy.run_precision_backtest(
                data["1h"], data["4h"], data["1m"], 
                vol_mult=vol, 
                atr_trail_mult=trail,
                risk_pct=risk,
                ema_period=ema
            )

            if trades:
                ret = ((strategy.capital / current_config["SEED"]) - 1) * 100
                mdd = calculate_mdd(equity_curve) * 100
                efficiency = ret / mdd if mdd > 0.1 else 0
                
                results.append({
                    "Symbol": sym,
                    "Vol_Mult": vol,
                    "Trail_Mult": trail,
                    "Risk": risk,
                    "EMA_Period": ema,
                    "Return(%)": round(ret, 2),
                    "MDD(%)": round(mdd, 2),
                    "Efficiency": round(efficiency, 2),
                    "Trades": len(trades) // 2
                })
        
        # Save intermediate results
        pd.DataFrame(results).to_csv("mega_optimization_results.csv", index=False)

    if not results:
        print("No results found.")
        return

    df_results = pd.DataFrame(results)
    # Find best parameters per symbol based on Return(%) or Efficiency. Let's use Efficiency as it balances risk.
    # User just said "best parameters", usually means best performance.
    best_results = df_results.loc[df_results.groupby("Symbol")["Efficiency"].idxmax()]
    
    best_results.to_csv("best_mega_report.csv", index=False)
    print("\nMega Optimization Complete!")
    print("\nBest Parameters per Symbol:")
    print(best_results[["Symbol", "Vol_Mult", "Trail_Mult", "EMA_Period", "Return(%)", "MDD(%)", "Efficiency"]].to_string(index=False))

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    mega_optimization(limit=limit)
