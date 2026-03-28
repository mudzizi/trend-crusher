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

def run_simulation_task(task):
    """
    Worker function for a single simulation task.
    """
    sym, mode_info, params, data_1m, days = task
    vol, trail, adx, don, ema, risk = params
    use_sniper, retest_maker, mode_name = mode_info
    
    temp_config = CONFIG.copy()
    temp_config.update({
        "SYMBOL": sym,
        "VOL_MULTIPLIER": vol,
        "TRAILING_ATR_MULT": trail,
        "ADX_FILTER_LEVEL": adx,
        "DONCHIAN_PERIOD": don,
        "EMA_TREND_PERIOD": ema,
        "RISK_PER_TRADE": risk,
        "SEED": CONFIG.get("SEED", 10000)
    })
    
    strategy = TrendCrusherV2(config=temp_config)
    trades, equity_curve, _ = strategy.run_streaming_backtest(
        data_1m,
        vol_mult=vol,
        atr_trail_mult=trail,
        adx_threshold=adx,
        donchian_period=don,
        ema_period=ema,
        risk_pct=risk,
        use_sniper=use_sniper,
        use_retest_maker=retest_maker
    )
    
    min_trades = max(3, days // 20)
    if len(trades) >= min_trades * 2:
        ret = ((strategy.capital / temp_config["SEED"]) - 1) * 100
        mdd = calculate_mdd(equity_curve) * 100
        efficiency = ret / mdd if mdd > 0.5 else 0
        
        return {
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
            "Trades": len(trades) // 2,
            "trades_raw": trades
        }
    return None

def run_mega_optimizer_v2(symbols_or_limit=10, days=90):
    start_time = time.time()
    notifier = TelegramNotifier()
    fetcher = BinanceDataFetcher()
    
    report_dir = os.path.join("reports", "MEGA_OPTIMIZATION")
    trades_dir = os.path.join(report_dir, "trades")
    os.makedirs(trades_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if isinstance(symbols_or_limit, list):
        symbols = symbols_or_limit
    else:
        symbols = fetcher.get_top_symbols(limit=int(symbols_or_limit))

    if not symbols: return
    notifier.notify_status(f"🚀 Mega-Turbo Optimizer Started\nTarget: {len(symbols)} Symbols\nTimeframe: {days} Days")

    # 1. Prepare Tasks
    print(f"\n[Stage 1] Syncing Market Data & Preparing Tasks...")
    all_tasks = []
    
    # Pre-define Grid
    vol_multipliers = [1.8, 2.2, 2.6]
    trailing_mults = [2.5, 3.5, 4.5]
    adx_thresholds = [15, 20, 25]
    donchian_periods = [10, 20, 30]
    ema_periods = [100, 200]
    modes = [(False, False, "Market"), (True, False, "Sniper"), (False, True, "Retest_Maker")]
    risk = 0.02

    for sym in symbols:
        fetcher.save_all(symbol=sym, days=days)
        clean_sym = sym.replace('/', '_').replace(':', '_')
        filename = f"{CONFIG['DATA_DIR']}/{clean_sym}_1m.csv"
        if not os.path.exists(filename): continue
        
        df_1m = pd.read_csv(filename)
        df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
        cutoff = datetime.now() - pd.Timedelta(days=days)
        data_1m = df_1m[df_1m['timestamp'] >= cutoff].copy()
        
        combinations = list(itertools.product(vol_multipliers, trailing_mults, adx_thresholds, donchian_periods, ema_periods))
        for combo in combinations:
            for mode in modes:
                all_tasks.append((sym, mode, combo + (risk,), data_1m, days))

    # 2. Parallel Execution (Task-level)
    print(f"\n[Stage 2] Running Parallel Simulation ({len(all_tasks)} total tasks)...")
    
    final_results = []
    symbol_best = {} # sym -> best_res
    
    with ProcessPoolExecutor() as executor:
        # Use chunksize for efficiency with many small tasks
        for idx, result in enumerate(executor.map(run_simulation_task, all_tasks, chunksize=10)):
            if idx % 100 == 0:
                print(f"Progress: {idx}/{len(all_tasks)} tasks processed ({(idx/len(all_tasks))*100:.1f}%)")
            
            if result:
                sym = result["Symbol"]
                final_results.append(result)
                if sym not in symbol_best or result["Efficiency"] > symbol_best[sym]["Efficiency"]:
                    symbol_best[sym] = result

    if not final_results:
        print("No profitably or valid configurations found.")
        return

    # 3. Reporting
    df_all = pd.DataFrame(final_results)
    best_configs = pd.DataFrame([res for res in symbol_best.values()])
    best_configs = best_configs.sort_values(by="Return(%)", ascending=False)
    
    filename = os.path.join(report_dir, f"mega_turbo_report_{timestamp}.csv")
    best_configs.to_csv(filename, index=False)
    
    # Save trades for best configs only
    for sym, res in symbol_best.items():
        clean_sym = sym.replace('/', '_')
        pd.DataFrame(res["trades_raw"]).to_csv(os.path.join(trades_dir, f"best_trades_{clean_sym}_{timestamp}.csv"), index=False)

    print(f"\n[Stage 3] Optimization Complete. Summary: {filename}")
    
    # 4. Telegram Notification
    msg = f"🏎️ *Mega-Turbo Optimizer: Complete*\n"
    msg += f"Processed {len(all_tasks)} tasks across {len(symbols)} symbols.\n\n"
    for idx, (index, row) in enumerate(best_configs.iterrows()):
        msg += f"🏆 *#{idx+1} {row['Symbol']} ({row['Mode']})*: *{row['Return(%)']:+.1f}%* (Eff: {row['Efficiency']})\n"
    
    msg += f"\n⏱️ Elapsed: {int(time.time() - start_time)}s"
    notifier.send_message(msg[:4000])
    
    print(f"\nTop Best Performer per Symbol:")
    print(best_configs[["Symbol", "Mode", "Return(%)", "MDD(%)", "Efficiency", "Trades"]].to_string(index=False))


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
