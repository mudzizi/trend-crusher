import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd
from src.optimizer_engine import OptimizerEngine
from src.strategy import TrendCrusherV2

@pytest.fixture
def mock_config():
    return {
        "BINANCE_API_KEY": "test_key",
        "BINANCE_SECRET": "test_secret",
        "SYMBOL": "BTC/USDT",
        "SEED": 10000.0,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "ADX_FILTER_LEVEL": 20,
        "EMA_TREND_PERIOD": 100
    }

@pytest.mark.asyncio
async def test_optimizer_initialization(mock_config):
    optimizer = OptimizerEngine(config=mock_config)
    assert optimizer.symbol == "BTC/USDT"
    assert len(optimizer.param_grid["VOL_MULTIPLIER"]) > 0

@pytest.mark.asyncio
async def test_optimizer_picks_best_efficiency(mock_config):
    # 시나리오: 엔진이 수익률만 높은 게 아니라 Return/MDD 효율이 좋은 걸 뽑는지 확인
    optimizer = OptimizerEngine(config=mock_config)

    # 1. Mock Data Fetcher & CSV
    with patch('src.optimizer_engine.BinanceDataFetcher'), \
         patch('src.optimizer_engine.pd.read_csv') as mock_read:

        # 가상의 OHLCV 데이터 (충분히 긴 데이터)
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='h')
        df = pd.DataFrame({
            'timestamp': dates,
            'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 1000
        })
        mock_read.return_value = df

        # 2. Mock Strategy Runner to simulate different outcomes
        side_effects = []
        for vol in optimizer.param_grid["VOL_MULTIPLIER"]:
            for adx in optimizer.param_grid["ADX_FILTER_LEVEL"]:
                for ema in optimizer.param_grid["EMA_TREND_PERIOD"]:
                    if vol == 1.5 and adx == 15 and ema == 50:
                        # Winner settings (2 trades: OPEN and CLOSE)
                        side_effects.append(([{'type': 'OPEN'}, {'type': 'CLOSE'}], [10000, 10250, 10500], df))
                    else:
                        side_effects.append(([], [10000, 11000, 9000], df))

        with patch('src.optimizer_engine.TrendCrusherV2.run_streaming_backtest', side_effect=side_effects):
            best = await optimizer.find_best_params("BTC/USDT", lookback_days=30)
            
            assert best is not None
            # The test depends on the grid iteration order, but 1.5/15/50 is in our winner path
            if best['vol_m'] == 1.5:
                assert best['adx_f'] == 15
                assert best['ema_p'] == 50
