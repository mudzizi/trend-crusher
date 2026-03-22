import pandas as pd
import numpy as np
import os
import itertools
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher
from src.telegram_utils import TelegramNotifier

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def optimize_single_symbol(sym, days=90):
    """
    Worker function to optimize a single symbol across a grid of parameters.
    Returns the best configuration found for this symbol.
    """
    print(f"--- [Worker] Starting optimization for {sym} ({days} days) ---")
    
    # 1. Load Data
    clean_sym = sym.replace('/', '_').replace(':', '_')
    data = {}
    timeframes = ["1h", "4h", "1m"]
    for tf in timeframes:
        filename = f"{CONFIG['DATA_DIR']}/{clean_sym}_{tf}.csv"
        if not os.path.exists(filename):
            print(f"Error: Data file missing for {sym} {tf}. Skipping...")
            return None
        df = pd.read_csv(filename)
        # Filter for the requested number of days
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        data[tf] = df[df['timestamp'] >= cutoff].copy()

    # 2. Define Grid (Slightly narrowed for speed)
    vol_multipliers = [1.8, 2.2, 2.6]
    trailing_mults = [2.5, 3.5, 4.5]
    adx_thresholds = [15, 20, 25]
    donchian_periods = [10, 20, 30]
    ema_periods = [100, 200]
    risk = 0.02
    
    combinations = list(itertools.product(vol_multipliers, trailing_mults, adx_thresholds, donchian_periods, ema_periods))
    total_combos = len(combinations)
    
    best_eff = -1
    best_config = None
    best_trades = None
    
    for idx, (vol, trail, adx, don, ema) in enumerate(combinations):
        if idx % 10 == 0:
            print(f"[{sym}] Progress: {idx}/{total_combos} combos tested...")
            
        # Run three modes: Market, Sniper, and Retest_Maker
        for mode_idx, (use_sniper, retest_maker) in enumerate([(False, False), (True, False), (False, True)]):
            mode_name = ["Market", "Sniper", "Retest_Maker"][mode_idx]
            
            temp_config = CONFIG.copy()
            temp_config.update({
                "SYMBOL": sym,
                "VOL_MULTIPLIER": vol,
                "TRAILING_ATR_MULT": trail,
                "ADX_FILTER_LEVEL": adx,
                "DONCHIAN_PERIOD": don,
                "EMA_TREND_PERIOD": ema,
                "RISK_PER_TRADE": risk
            })
            
            strategy = TrendCrusherV2(config=temp_config)
            trades, equity_curve = strategy.run_precision_backtest(
                data["1h"], data["4h"], data["1m"],
                vol_mult=vol,
                atr_trail_mult=trail,
                risk_pct=risk,
                ema_period=ema,
                adx_threshold=adx,
                donchian_period=don,
                use_sniper=use_sniper,
                retest_maker=retest_maker
            )
            
            min_trades = max(3, days // 20) 
            if len(trades) >= min_trades * 2:
                ret = ((strategy.capital / CONFIG["SEED"]) - 1) * 100
                mdd = calculate_mdd(equity_curve) * 100
                efficiency = ret / mdd if mdd > 0.5 else 0
                
                if efficiency > best_eff:
                    best_eff = efficiency
                    best_trades = trades
                    best_config = {
                        "Symbol": sym,
                        "Mode": mode_name,
                        "Vol_Mult": vol,
                        "Trail_Mult": trail,
                        "ADX": adx,
                        "Donchian": don,
                        "EMA": ema,
                        "Return(%)": round(ret, 2),
                        "MDD(%)": round(mdd, 2),
                        "Efficiency": round(efficiency, 2),
                        "Trades": len(trades) // 2
                    }
    
    if best_config:
        print(f"--- [Worker] {sym} Best Efficiency: {best_eff:.2f} (Ret: {best_config['Return(%)']}%) ---")
    return best_config, best_trades

def run_mega_optimizer_v2(symbols_or_limit=10, days=90):
    start_time = time.time()
    notifier = TelegramNotifier()
    fetcher = BinanceDataFetcher()
    
    # Structured Save Path
    report_dir = os.path.join("reports", "MEGA_OPTIMIZATION")
    trades_dir = os.path.join(report_dir, "trades")
    os.makedirs(trades_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 1. Discovery
    if isinstance(symbols_or_limit, list):
        symbols = symbols_or_limit
        print(f"Targeting specified symbols: {symbols}")
    else:
        limit = int(symbols_or_limit)
        symbols = fetcher.get_top_symbols(limit=limit)
        print(f"Targeting top {limit} symbols by volume: {symbols}")

    if not symbols:
        print("No symbols found.")
        return
    
    notifier.notify_status(f"🚀 Mega-Optimizer V2 Started\nTarget: {len(symbols)} Symbols\nTimeframe: {days} Days")

    # 2. Data Collection
    print(f"\n[Stage 1] Syncing Market Data ({days} days)...")
    for sym in symbols:
        fetcher.save_all(symbol=sym, days=days)
    
    # 3. Parallel Optimization
    print(f"\n[Stage 2] Running Parallel Optimization on {len(symbols)} Symbols...")
    
    with ProcessPoolExecutor() as executor:
        worker_results = list(executor.map(optimize_single_symbol, symbols, itertools.repeat(days)))
    
    final_results = []
    for res, trades in worker_results:
        if res is not None:
            final_results.append(res)
            # Save Raw Trades for the best config
            clean_sym = res["Symbol"].replace('/', '_')
            trade_file = os.path.join(trades_dir, f"trades_{clean_sym}_{timestamp}.csv")
            pd.DataFrame(trades).to_csv(trade_file, index=False)
    
    if not final_results:
        print("No profitable or valid configurations found.")
        notifier.notify_error("Mega-Optimizer failed to find valid configurations.")
        return

    # 4. Reporting
    df_results = pd.DataFrame(final_results)
    
    # Sort by Return(%) as requested
    df_results = df_results.sort_values(by="Return(%)", ascending=False)
    
    filename = os.path.join(report_dir, f"mega_report_{timestamp}.csv")
    df_results.to_csv(filename, index=False)
    print(f"\n[Stage 3] Optimization Complete. Summary: {filename}")
    print(f"Raw trades saved in: {trades_dir}")
    
    # 5. Full Sentinel Report (All Symbols sorted by Return)
    msg = f"🕵️ *Mega-Optimizer V2: Full Performance Report*\n"
    msg += f"_(Sorted by Return (%) over {days} days)_\n\n"
    
    for idx, (index, row) in enumerate(df_results.iterrows()):
        msg += (
            f"🏆 *#{idx+1} {row['Symbol']} ({row['Mode']})*\n"
            f"• *Return: {row['Return(%)']:+.1f}%*\n"
            f"• MDD: {row['MDD(%)']:.1f}%\n"
            f"• Efficiency: {row['Efficiency']:.2f}\n"
            f"• Trades: {row['Trades']}\n"
            f"• Config: `V:{row['Vol_Mult']}, T:{row['Trail_Mult']}, A:{row['ADX']}, D:{row['Donchian']}`\n\n"
        )
    
    msg += f"⏱️ Total Time: {int(time.time() - start_time)}s"
    
    # If the message is too long for Telegram (4096 chars), send in chunks or just the summary
    if len(msg) > 4000:
        notifier.send_message("📊 *Optimization Complete!* Results are too long for one message. Please check the CSV report for full details.")
        # Send top 10 as a compromise
        summary_msg = "🔝 *Top 10 Performers (by Return):*\n\n" + "\n".join(msg.split("\n\n")[:20])
        notifier.send_message(summary_msg)
    else:
        notifier.send_message(msg)
    
    print(f"\nFull Optimization Results (Sorted by Return):")
    print(df_results[["Symbol", "Mode", "Return(%)", "MDD(%)", "Efficiency", "Trades"]].to_string(index=False))

if __name__ == "__main__":
    import sys
    arg1 = sys.argv[1] if len(sys.argv) > 1 else "10"
    days_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    
    if arg1.isdigit():
        run_mega_optimizer_v2(symbols_or_limit=int(arg1), days=days_arg)
    else:
        # Process symbol list (e.g., "BTC/USDT,ETH/USDT" or "BTC,ETH")
        raw_symbols = arg1.split(',')
        formatted_symbols = []
        for s in raw_symbols:
            s = s.strip().upper()
            if '/' not in s:
                s = f"{s}/USDT"
            formatted_symbols.append(s)
        run_mega_optimizer_v2(symbols_or_limit=formatted_symbols, days=days_arg)
