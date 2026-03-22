import pandas as pd
import numpy as np
import asyncio
from src.strategy import TrendCrusherV2
from src.config import CONFIG

async def run_experiment():
    symbol = "TRUMP/USDT"
    clean_sym = symbol.replace('/', '_')
    
    # Load data
    df_1h = pd.read_csv(f"data/{clean_sym}_1h.csv")
    df_4h = pd.read_csv(f"data/{clean_sym}_4h.csv")
    df_1m = pd.read_csv(f"data/{clean_sym}_1m.csv")
    
    # 1. Base Strategy (Market Mode)
    strategy = TrendCrusherV2(config=CONFIG)
    
    # Experiment A: Market Mode + Ultra Low Slippage (0.01%)
    # Note: _open_position uses internal effective_slippage logic.
    # In MARKET mode, it's currently hardcoded to 0.0005. 
    # I will monkeypatch it or wrap it for this experiment.
    
    original_open = strategy._open_position
    
    def patched_open_001(direction, price, sl_price, timestamp, risk_pct, is_sniper=False, is_maker=False):
        # Force slippage to 0.01% for Market
        effective_slippage = 0.0001 if not is_maker else 0
        
        side = 'LONG' if direction == 1 else 'SHORT'
        current_fee_rate = 0.0005 # Taker fee
        
        strategy.entry_price = price * (1 + (effective_slippage * direction))
        strategy.sl_price = sl_price
        strategy.quantity = strategy.calculate_position_size(strategy.entry_price, strategy.sl_price, risk_pct)
        
        if strategy.quantity > 0:
            strategy.capital -= strategy.entry_price * strategy.quantity * current_fee_rate
            strategy.position = direction
            strategy.max_price_seen = strategy.entry_price
            strategy.min_price_seen = strategy.entry_price
            strategy.trades.append({'time': timestamp, 'type': 'OPEN', 'side': side, 'price': strategy.entry_price, 'qty': strategy.quantity, 'is_maker': is_maker})

    strategy._open_position = patched_open_001
    
    print(f"\n🧪 [Experiment] Market Mode with 0.01% Slippage (TRUMP)")
    trades, equity_curve = strategy.run_precision_backtest(
        df_1h, df_4h, df_1m, 
        use_sniper=False, # Market mode
        retest_maker=False
    )
    
    final_return = ((strategy.capital / strategy.initial_capital) - 1) * 100
    mdd = (np.max(np.maximum.accumulate(equity_curve) - equity_curve) / (np.max(equity_curve) + 1e-10)) * 100
    
    print(f"Result: Return: {final_return:+.2f}% | MDD: {mdd:.2f}% | Trades: {len([t for t in trades if t['type']=='CLOSE'])}")

if __name__ == "__main__":
    asyncio.run(run_experiment())
