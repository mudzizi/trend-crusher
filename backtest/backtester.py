import pandas as pd
import numpy as np
import os
from src.strategy import AggressiveVBOStrategy

class MultiSymbolOptimizer:
    def __init__(self, symbols, timeframe='1h'):
        self.symbols = symbols
        self.timeframe = timeframe
        self.results = []

    def calculate_mdd(self, equity_curve):
        if not equity_curve: return 0
        curve = np.array(equity_curve)
        peak = np.maximum.accumulate(curve)
        drawdown = (peak - curve) / (peak + 1e-10)
        return np.max(drawdown)

    def run(self):
        for sym in self.symbols:
            clean_sym = sym.replace('/', '_')
            f1h = f"data/{clean_sym}_1h.csv"
            f4h = f"data/{clean_sym}_4h.csv"
            
            if not os.path.exists(f1h) or not os.path.exists(f4h):
                print(f"Skipping {sym}: Files not found.")
                continue
            
            df_1h = pd.read_csv(f1h)
            df_4h = pd.read_csv(f4h)
            
            strategy = AggressiveVBOStrategy()
            trades, equity_curve = strategy.run(df_1h, df_4h)
            
            total_trades = len([t for t in trades if t['type'] == 'CLOSE'])
            wins = 0
            last_open_price = 0
            last_open_type = ''
            for t in trades:
                if 'OPEN' in t['type']:
                    last_open_price = t['price']
                    last_open_type = t['type']
                elif 'CLOSE' in t['type']:
                    if last_open_type == 'OPEN_LONG' and t['price'] > last_open_price: wins += 1
                    elif last_open_type == 'OPEN_SHORT' and t['price'] < last_open_price: wins += 1
            
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
            mdd = self.calculate_mdd(equity_curve) * 100
            
            self.results.append({
                'Symbol': sym,
                'Total Trades': total_trades,
                'Win Rate (%)': round(win_rate, 2),
                'Final Return (%)': round(final_return, 2),
                'MDD (%)': round(mdd, 2)
            })
            
        return pd.DataFrame(self.results)

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']
    optimizer = MultiSymbolOptimizer(symbols)
    summary = optimizer.run()
    print("\n[Aggressive Breakout] 1-Year Multi-Symbol Performance:")
    print(summary.to_string(index=False))
