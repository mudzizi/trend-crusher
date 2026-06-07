import pandas as pd
import numpy as np
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher

logger = logging.getLogger(__name__)

def _run_single_search(task):
    """
    Worker task for parallel parameter grid search.
    Must be at top-level for pickling support in ProcessPoolExecutor.
    """
    try:
        config, df_check, pre_calculated_ind, vol_m, adx_f, ema_p, seed = task
        test_cfg = config.copy()
        test_cfg.update({
            "VOL_MULTIPLIER": vol_m,
            "ADX_FILTER_LEVEL": adx_f,
            "EMA_TREND_PERIOD": ema_p,
            "USE_ADAPTIVE_TRAIL": True
        })
        strategy = TrendCrusherV2(config=test_cfg)
        trades, equity_curve, _ = strategy.run_streaming_backtest(df_check, pre_calculated_ind=pre_calculated_ind)

        if len(trades) >= 2:
            final_return = ((strategy.capital / seed) - 1) * 100
            # Calculate MDD
            curve = np.array(equity_curve)
            peak = np.maximum.accumulate(curve)
            drawdown = (peak - curve) / (peak + 1e-10)
            mdd = np.max(drawdown) * 100
            efficiency = final_return / (mdd + 0.1)

            return {
                "vol_m": vol_m,
                "adx_f": adx_f,
                "ema_p": ema_p,
                "return": final_return,
                "mdd": mdd,
                "efficiency": efficiency,
                "trades": len(trades) // 2
            }
    except Exception as e:
        pass
    return None

class OptimizerEngine:
    """
    Finds the best performing parameters for a given symbol based on recent market data.
    Implements Walk-Forward Optimization logic.
    """
    def __init__(self, config=CONFIG):
        self.config = config
        self.symbol = config.get("SYMBOL", "BTC/USDT") # Default for tests
        self.param_grid = {
            "VOL_MULTIPLIER": [1.5, 2.0, 2.5, 3.0],
            "ADX_FILTER_LEVEL": [15, 20, 25, 30],
            "EMA_TREND_PERIOD": [50, 100, 200]
        }

    async def find_best_params(self, symbol, lookback_days=30):
        """
        Runs a parallelized grid search over the last N days of data to find optimal settings.
        Optimized via pre-calculating indicators per EMA_TREND_PERIOD and multiprocessing.
        """
        self.symbol = symbol # Update for tracking
        logger.info(f"🧠 Optimizing {symbol} using last {lookback_days} days...")
        
        # 1. Update/Fetch latest data
        fetcher = BinanceDataFetcher(config=self.config)
        fetcher.save_all() # Ensure local CSVs are fresh
        
        clean_sym = symbol.replace('/', '_')
        try:
            df_check = pd.read_csv(f"data/{clean_sym}_1m.csv")
        except FileNotFoundError:
            logger.error(f"Data files not found for {symbol}")
            return None

        # Filter for recent N days
        df_check['timestamp'] = pd.to_datetime(df_check['timestamp'])
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
        df_check = df_check[df_check['timestamp'] > cutoff]

        if df_check.empty:
            logger.error(f"Filtered data is empty for {symbol}")
            return None

        # 2. Pre-calculate indicators per EMA_TREND_PERIOD to eliminate redundant Series operations
        ind_cache = {}
        for ema_p in self.param_grid["EMA_TREND_PERIOD"]:
            test_cfg = self.config.copy()
            test_cfg["EMA_TREND_PERIOD"] = ema_p
            strategy = TrendCrusherV2(config=test_cfg)
            
            df_1h_ind = strategy.calculate_indicators(
                get_all_base_bars(df_check, test_cfg.get("SIGNAL_TIMEFRAME", "1h"), True), 
                get_all_base_bars(df_check, test_cfg.get("TREND_TIMEFRAME", "4h"), True), 
                test_cfg
            )
            ind_cache[ema_p] = df_1h_ind

        # 3. Prepare tasks for multiprocessing
        tasks = []
        seed = self.config.get("SEED", 200.0)
        for ema_p in self.param_grid["EMA_TREND_PERIOD"]:
            pre_calculated_ind = ind_cache[ema_p]
            for vol_m in self.param_grid["VOL_MULTIPLIER"]:
                for adx_f in self.param_grid["ADX_FILTER_LEVEL"]:
                    tasks.append((
                        self.config,
                        df_check,
                        pre_calculated_ind,
                        vol_m,
                        adx_f,
                        ema_p,
                        seed
                    ))

        # 4. Execute grid search in parallel
        results = []
        cpu_count = os.cpu_count() or 4
        max_workers = min(cpu_count, len(tasks))
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Map returns elements in submission order
            for res in executor.map(_run_single_search, tasks):
                if res is not None:
                    results.append(res)

        if not results:
            return None

        # 5. Pick the best based on Efficiency
        best = max(results, key=lambda x: x['efficiency'])
        logger.info(f"🏆 Best for {symbol}: Vol={best['vol_m']}, ADX={best['adx_f']}, EMA={best['ema_p']} | Ret={best['return']:.2f}%, MDD={best['mdd']:.2f}%")
        
        return best

    def _calculate_mdd(self, equity_curve):
        if not equity_curve: return 0
        curve = np.array(equity_curve)
        peak = np.maximum.accumulate(curve)
        drawdown = (peak - curve) / (peak + 1e-10)
        return np.max(drawdown)
