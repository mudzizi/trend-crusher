import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta
import argparse

# Add project root to path for imports
sys.path.append(os.getcwd())

from src.strategy_macd import TrendCrusherMACD
from src.config import CONFIG
from src.visualizer import TradingVisualizer
from src.data_fetcher import BinanceDataFetcher

def calculate_mdd(equity_curve):
    if not equity_curve: return 0.0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_backtest_macd(symbol, days=365, timeframe="1h", seed=10000.0, sl_pct=0.02, atr_mult=2.0, adx_threshold=20.0, chop_threshold=50.0, use_squeeze=False, start_date=None, end_date=None, use_ema=False, ema_span=200):
    if start_date:
        start_dt = pd.to_datetime(start_date)
        sync_days = (datetime.now() - start_dt).days + 15
    else:
        start_dt = datetime.now() - timedelta(days=days)
        sync_days = days + 10
        
    if end_date:
        end_dt = pd.to_datetime(end_date)
    else:
        end_dt = datetime.now()

    print(f"\n🚀 [MACD] Backtesting {symbol} | Timeframe: {timeframe} | Period: {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')} | SL: {sl_pct*100}% | ATR Mult: {atr_mult} | ADX Thresh: {adx_threshold} | CHOP Thresh: {chop_threshold} | Squeeze Filter: {use_squeeze} | EMA Filter: {use_ema} ({ema_span})")
    
    # 1. Sync Data (Fast Hourly Sync)
    fetcher = BinanceDataFetcher()
    try:
        fetcher.save_ohlcv(symbol=symbol, timeframe="1h", days=sync_days)
    except Exception as e:
        print(f"Sync failed (falling back to existing file): {e}")
            
    clean_sym = symbol.replace('/', '_')
    data_path = f"data/{clean_sym}_1h.csv"
    
    if not os.path.exists(data_path):
        print(f"Error: Data file {data_path} not found.")
        return None
        
    df_1h = pd.read_csv(data_path, parse_dates=['timestamp'])
    df_1h = df_1h[(df_1h['timestamp'] >= start_dt) & (df_1h['timestamp'] <= end_dt)].copy()
    
    if df_1h.empty:
        print(f"Error: No data for {symbol} in the requested period.")
        return None
        
    # 2. Strategy Setup
    test_config = CONFIG.copy()
    test_config["SEED"] = seed
    test_config["SIGNAL_TIMEFRAME"] = timeframe
    test_config["STOP_LOSS_PCT"] = sl_pct
    test_config["ATR_SL_MULT"] = atr_mult
    test_config["ADX_THRESHOLD"] = adx_threshold
    test_config["CHOP_THRESHOLD"] = chop_threshold
    test_config["USE_SQUEEZE_FILTER"] = use_squeeze
    test_config["USE_EMA_FILTER"] = use_ema
    test_config["EMA_FILTER_SPAN"] = ema_span
    
    strategy = TrendCrusherMACD(config=test_config)
    
    # 3. Run Engine
    trades, equity_curve, df_ind = strategy.run_streaming_backtest(df_1h, timeframe=timeframe)
    
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
    
    # Ensure equity curve maps to timestamps.
    # In candle-level backtesting, length of equity_curve matches df_sig.
    # We map them index-to-index.
    equity_records = []
    for i, val in enumerate(equity_curve):
        if i < len(df_ind):
            ts = df_ind.iloc[i]['timestamp']
        else:
            ts = df_ind.iloc[-1]['timestamp']
        equity_records.append({'timestamp': ts, 'balance': val})
    equity_df = pd.DataFrame(equity_records)
    
    if 'timestamp' not in df_ind.columns:
        df_ind = df_ind.reset_index()
        
    report_path = viz.generate_report(df_ind, trades_df, equity_df, f"{symbol}_MACD_{timeframe}")
    
    # 6. Summary
    final_cap = strategy.capital
    ret = ((final_cap / seed) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    
    wins = [t for t in processed_trades if t['pnl_pct'] > 0]
    win_rate = (len(wins) / len(processed_trades) * 100) if processed_trades else 0.0
    
    print("\n" + "="*50)
    print(f" Result for {symbol} (MACD {timeframe})")
    print("="*50)
    print(f"Initial Capital: {seed:,.2f} USDT")
    print(f"Final Capital:   {final_cap:,.2f} USDT")
    print(f"Total Return:    {ret:+.2f}%")
    print(f"Max Drawdown:    {mdd:.2f}%")
    print(f"Total Trades:    {len(processed_trades)}")
    print(f"Win Rate:        {win_rate:.2f}%")
    print(f"Efficiency:      {ret/(mdd+0.1):.2f}")
    print(f"Report Saved:    {report_path}")
    print("="*50)
    
    return {
        "Symbol": symbol,
        "Timeframe": timeframe,
        "Return": f"{ret:+.2f}%",
        "MDD": f"{mdd:.2f}%",
        "Trades": len(processed_trades),
        "Win Rate": f"{win_rate:.2f}%",
        "Eff": round(ret/(mdd+0.1), 2)
    }

def main():
    parser = argparse.ArgumentParser(description="MACD Strategy Backtester")
    parser.add_argument("--symbol", type=str, default="ETH/USDT", help="Symbol or list of symbols (comma separated)")
    parser.add_argument("--timeframe", type=str, choices=["1h", "4h"], default="1h", help="Timeframe (1h or 4h)")
    parser.add_argument("--days", type=int, default=365, help="Backtest period in days")
    parser.add_argument("--seed", type=float, default=10000.0, help="Initial seed capital")
    parser.add_argument("--sl-pct", type=float, default=0.02, help="Stop Loss percentage (e.g. 0.02 for 2%)")
    parser.add_argument("--atr-mult", type=float, default=2.0, help="ATR Stop Loss multiplier (default 2.0, 0.0 to disable)")
    parser.add_argument("--adx-threshold", type=float, default=20.0, help="ADX filter threshold (default 20.0, 0.0 to disable)")
    parser.add_argument("--chop-threshold", type=float, default=50.0, help="Choppiness Index threshold (default 50.0, 0.0 to disable)")
    parser.add_argument("--use-squeeze", action="store_true", help="Enable Volatility Squeeze filter (BB inside KC)")
    parser.add_argument("--use-ema", action="store_true", help="Enable EMA Trend Filter (long-term trend)")
    parser.add_argument("--ema-span", type=int, default=200, help="EMA filter span (default 200)")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    symbols = args.symbol.split(',')
    results = []
    
    for s in symbols:
        res = run_backtest_macd(s.strip().upper(), args.days, args.timeframe, args.seed, args.sl_pct, args.atr_mult, args.adx_threshold, args.chop_threshold, args.use_squeeze, args.start_date, args.end_date, args.use_ema, args.ema_span)
        if res:
            results.append(res)
            
    if len(results) > 1:
        print("\n" + "📊 ALL SYMBOLS SUMMARY " + "="*30)
        print(pd.DataFrame(results).to_string(index=False))

if __name__ == "__main__":
    main()
