import pandas as pd
import numpy as np
import os
import asyncio
from datetime import datetime, timedelta
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher
from src.telegram_utils import TelegramNotifier

async def run_comprehensive_backtest():
    notifier = TelegramNotifier()
    fetcher = BinanceDataFetcher()
    #symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "TRUMP/USDT", "XAU/USDT"]
    symbols = ["TRUMP/USDT"]
    days = 365
    
    report_lines = [f"📊 *365-Day Backtest Report (v{CONFIG['VERSION']})*\n"]
    total_final_return = 0
    
    for symbol in symbols:
        print(f"Testing {symbol}...")
        clean_sym = symbol.replace('/', '_')
        
        # 1. Ensure Data
        try:
            # Sync call to save_all (internally fetches 1h, 4h, 1m)
            fetcher.save_all(symbol, days=days)
            
            df_1h = pd.read_csv(f"data/{clean_sym}_1h.csv")
            df_4h = pd.read_csv(f"data/{clean_sym}_4h.csv")
            df_1m = pd.read_csv(f"data/{clean_sym}_1m.csv")
            
            # 2. Get Settings for this symbol
            settings = CONFIG.get("SYMBOL_SETTINGS", {}).get(symbol, CONFIG.copy())
            
            # 3. Run Strategy
            strategy = TrendCrusherV2(config=CONFIG)
            # Inject symbol specific settings
            kwargs = {
                'use_sniper': settings.get('USE_SNIPER', True),
                'retest_maker': settings.get('USE_RETEST_MAKER', False),
                'vol_mult': settings.get('VOL_MULTIPLIER', 2.0),
                'atr_trail_mult': settings.get('TRAILING_ATR_MULT', 4.5),
                'ema_period': settings.get('EMA_TREND_PERIOD', 100),
                'adx_threshold': settings.get('ADX_FILTER_LEVEL', 15),
                'risk_pct': settings.get('RISK_PER_TRADE', 0.02)
            }
            
            trades, equity_curve = strategy.run_precision_backtest(df_1h, df_4h, df_1m, **kwargs)
            
            # 4. Calculate Metrics
            final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
            
            curve = np.array(equity_curve)
            peak = np.maximum.accumulate(curve)
            drawdown = (peak - curve) / (peak + 1e-10)
            mdd = np.max(drawdown) * 100
            
            total_trades = len([t for t in trades if t['type'] == 'CLOSE'])
            wins = len([t for t in trades if t.get('pnl_usdt', 0) > 0])
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            mode_str = "RETEST" if kwargs['retest_maker'] else ("SNIPER" if kwargs['use_sniper'] else "MARKET")
            
            report_lines.append(
                f"• *{symbol}* ({mode_str})\n"
                f"  Return: {final_return:+.2f}% | MDD: {mdd:.2f}%\n"
                f"  Trades: {total_trades} | WinRate: {win_rate:.1f}%\n"
            )
            total_final_return += final_return
            
        except Exception as e:
            print(f"Error testing {symbol}: {e}")
            report_lines.append(f"• *{symbol}*: Error occurred during backtest.\n")

    avg_return = total_final_return / len(symbols)
    report_lines.append(f"\n📈 *Average Portfolio Return: {avg_return:+.2f}%*")
    
    full_report = "\n".join(report_lines)
    print("\n" + full_report)
    
    # Send to Telegram
    try:
        notifier.send_message(full_report)
        print("✅ Report sent to Telegram.")
    except Exception as te:
        print(f"❌ Failed to send Telegram message: {te}")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_backtest())
