import pandas as pd
import numpy as np
import logging
import os
from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

logger = logging.getLogger(__name__)

class OptimizerEngine:
    """
    Finds the best performing parameters for a given symbol based on recent market data.
    Implements Walk-Forward Optimization logic.
    """
    def __init__(self, config=CONFIG):
        self.config = config
        self.param_grid = {
            "VOL_MULTIPLIER": [1.5, 2.0, 2.5, 3.0],
            "ADX_FILTER_LEVEL": [15, 20, 25, 30],
            "EMA_TREND_PERIOD": [50, 100, 200]
        }

    async def find_best_params(self, symbol, lookback_days=30):
        """
        Runs a grid search over the last N days of data to find optimal settings.
        """
        logger.info(f"🧠 Optimizing {symbol} using last {lookback_days} days...")
        
        # 1. Update/Fetch latest data
        fetcher = BinanceDataFetcher(config=self.config)
        fetcher.save_all() # Ensure local CSVs are fresh
        
        clean_sym = symbol.replace('/', '_')
        try:
            df_sig = pd.read_csv(f"data/{clean_sym}_1h.csv")
            df_trend = pd.read_csv(f"data/{clean_sym}_4h.csv")
            df_check = pd.read_csv(f"data/{clean_sym}_1m.csv")
        except FileNotFoundError:
            logger.error(f"Data files not found for {symbol}")
            return None

        # Filter for recent N days
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
        df_sig['timestamp'] = pd.to_datetime(df_sig['timestamp'])
        df_sig = df_sig[df_sig['timestamp'] > cutoff]
        # (Other DFs will be aligned inside the strategy runner)

        results = []
        
        # 2. Grid Search
        for vol_m in self.param_grid["VOL_MULTIPLIER"]:
            for adx_f in self.param_grid["ADX_FILTER_LEVEL"]:
                for ema_p in self.param_grid["EMA_TREND_PERIOD"]:
                    
                    test_cfg = self.config.copy()
                    test_cfg.update({
                        "VOL_MULTIPLIER": vol_m,
                        "ADX_FILTER_LEVEL": adx_f,
                        "EMA_TREND_PERIOD": ema_p,
                        "USE_ADAPTIVE_TRAIL": True # Always use safety features
                    })
                    
                    strategy = TrendCrusherV2(config=test_cfg)
                    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)
                    
                    if not equity_curve: continue
                    
                    final_return = ((equity_curve[-1] / test_cfg["SEED"]) - 1) * 100
                    mdd = self._calculate_mdd(equity_curve) * 100
                    efficiency = final_return / (mdd + 1e-6) # Return/MDD Ratio
                    
                    results.append({
                        "vol_m": vol_m,
                        "adx_f": adx_f,
                        "ema_p": ema_p,
                        "return": final_return,
                        "mdd": mdd,
                        "efficiency": efficiency,
                        "trades": len(trades) // 2
                    })

        if not results:
            return None

        # 3. Pick the best based on Efficiency
        best = max(results, key=lambda x: x['efficiency'])
        logger.info(f"🏆 Best for {symbol}: Vol={best['vol_m']}, ADX={best['adx_f']}, EMA={best['ema_p']} | Ret={best['return']:.2f}%, MDD={best['mdd']:.2f}%")
        
        return best

    def _calculate_mdd(self, equity_curve):
        curve = np.array(equity_curve)
        peak = np.maximum.accumulate(curve)
        drawdown = (peak - curve) / (peak + 1e-10)
        return np.max(drawdown)
