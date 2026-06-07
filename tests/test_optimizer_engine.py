import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from src.optimizer_engine import OptimizerEngine

@pytest.fixture
def mock_config():
    return {
        "SEED": 10000.0,
        "RISK_PER_TRADE": 0.02,
        "VOL_MULTIPLIER": 2.0,
        "ADX_FILTER_LEVEL": 20.0,
        "EMA_TREND_PERIOD": 5,  # Small value for testing
        "DONCHIAN_PERIOD": 5,   # Small value for testing
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "USE_ADAPTIVE_TRAIL": True,
        "SYMBOL": "BTC/USDT"
    }

@pytest.fixture
def mock_ohlcv_data():
    # Create 5 days of 1-minute bar data (5 * 24 * 60 = 7200 rows)
    # This is enough to resample into 1h and 4h bars with periods of 5
    date_range = pd.date_range(end=pd.Timestamp.now(), periods=7500, freq='1min')
    
    # Generate some simple trends so strategy can trigger entry/exits
    np.random.seed(42)
    close_prices = 50000.0 + np.cumsum(np.random.randn(7500) * 15)
    open_prices = close_prices - np.random.randn(7500) * 5
    high_prices = np.maximum(open_prices, close_prices) + np.abs(np.random.randn(7500) * 10)
    low_prices = np.minimum(open_prices, close_prices) - np.abs(np.random.randn(7500) * 10)
    volume = np.random.randint(10, 1000, size=7500)
    
    df = pd.DataFrame({
        'timestamp': date_range,
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume
    })
    return df

@pytest.mark.asyncio
async def test_optimizer_engine_find_best_params(mock_config, mock_ohlcv_data):
    # Instantiate OptimizerEngine with our test config
    engine = OptimizerEngine(config=mock_config)
    
    # Shrink the parameter grid for rapid test execution
    engine.param_grid = {
        "VOL_MULTIPLIER": [1.5, 2.0],
        "ADX_FILTER_LEVEL": [15, 20],
        "EMA_TREND_PERIOD": [5, 10]
    }
    
    # Mock BinanceDataFetcher.save_all to do nothing
    with patch('src.optimizer_engine.BinanceDataFetcher') as MockFetcher:
        mock_fetcher_instance = MagicMock()
        MockFetcher.return_value = mock_fetcher_instance
        
        # Mock pd.read_csv to return our mock dataframe
        with patch('pandas.read_csv', return_value=mock_ohlcv_data):
            # Run the optimizer
            best_params = await engine.find_best_params("BTC/USDT", lookback_days=4)
            
            # Verify results
            assert best_params is not None
            assert "vol_m" in best_params
            assert "adx_f" in best_params
            assert "ema_p" in best_params
            assert "return" in best_params
            assert "mdd" in best_params
            assert "efficiency" in best_params
            assert "trades" in best_params
            
            # Verify parameter values are selected from the grid
            assert best_params["vol_m"] in engine.param_grid["VOL_MULTIPLIER"]
            assert best_params["adx_f"] in engine.param_grid["ADX_FILTER_LEVEL"]
            assert best_params["ema_p"] in engine.param_grid["EMA_TREND_PERIOD"]
            
            # Assert save_all was called
            mock_fetcher_instance.save_all.assert_called_once()
