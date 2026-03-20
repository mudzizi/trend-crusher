import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from src.optimizer_engine import OptimizerEngine
from scripts.live_bot_async import SymbolBotAsync

@pytest.fixture
def mock_config():
    return {
        "SEED": 10000.0,
        "VOL_MULTIPLIER": 2.5,
        "ADX_FILTER_LEVEL": 20,
        "EMA_TREND_PERIOD": 100,
        "SIGNAL_TIMEFRAME": "1h",
        "TREND_TIMEFRAME": "4h",
        "SYMBOL_SETTINGS": {
            "BTC/USDT": {"ALLOCATED_SEED": 5000.0}
        }
    }

@pytest.mark.asyncio
async def test_optimizer_picks_best_efficiency(mock_config):
    # 시나리오: 엔진이 수익률만 높은 게 아니라 Return/MDD 효율이 좋은 걸 뽑는지 확인
    optimizer = OptimizerEngine(config=mock_config)
    
    # 1. Mock Data Fetcher & CSV
    with patch('src.optimizer_engine.BinanceDataFetcher'), \
         patch('src.optimizer_engine.pd.read_csv') as mock_read:
        
        # 가상의 OHLCV 데이터 (충분히 긴 데이터)
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='H')
        df = pd.DataFrame({
            'timestamp': dates,
            'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 1000
        })
        mock_read.return_value = df
        
        # 2. Mock Strategy Runner to simulate different outcomes
        # index 0: High Return but High MDD (Eff: 100/50 = 2)
        # index 1: Low Return but Very Low MDD (Eff: 50/10 = 5) -> WINNER
        side_effects = []
        for vol in optimizer.param_grid["VOL_MULTIPLIER"]:
            for adx in optimizer.param_grid["ADX_FILTER_LEVEL"]:
                for ema in optimizer.param_grid["EMA_TREND_PERIOD"]:
                    if vol == 1.5 and adx == 15 and ema == 50:
                        # Winner settings
                        side_effects.append(([], [10000, 10250, 10500])) # Ret 5%, MDD 0% (High efficiency)
                    else:
                        side_effects.append(([], [10000, 11000, 9000])) # Ret -10%, MDD 20% (Low efficiency)

        with patch('src.optimizer_engine.TrendCrusherV2.run_precision_backtest', side_effect=side_effects):
            best = await optimizer.find_best_params("BTC/USDT", lookback_days=30)
            
            assert best is not None
            assert best['vol_m'] == 1.5
            assert best['adx_f'] == 15
            assert best['ema_p'] == 50
            assert best['efficiency'] > 0

def test_symbol_bot_hot_reload(mock_config):
    # 시나리오: 봇의 설정을 실시간으로 바꿨을 때 반영되는지 확인
    from scripts.live_bot_async import SymbolBotAsync
    
    mock_exchange = MagicMock()
    mock_db = MagicMock()
    mock_notifier = MagicMock()
    mock_pm = MagicMock()
    
    # 클래스 직접 초기화 확인
    bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    
    # 초기 설정 확인 (mock_config fixture 사용)
    assert bot.settings["VOL_MULTIPLIER"] == 2.5
    
    # 핫 리로드 수행
    new_params = {"VOL_MULTIPLIER": 3.5, "ADX_FILTER_LEVEL": 30}
    bot.hot_reload_settings(new_params)
    
    # 변경된 설정 확인
    assert bot.settings["VOL_MULTIPLIER"] == 3.5
    assert bot.settings["ADX_FILTER_LEVEL"] == 30
    assert bot.settings["EMA_TREND_PERIOD"] == 100 
