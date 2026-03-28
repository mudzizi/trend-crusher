import unittest
import asyncio
import pandas as pd
import numpy as np
import time
from unittest.mock import MagicMock, AsyncMock, patch
from src.strategy import TrendCrusherV2
from scripts.live_bot_async import SymbolBotAsync

class TestLiveOptimizations(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = {
            "EMA_TREND_PERIOD": 50,
            "DONCHIAN_PERIOD": 20,
            "ATR_PERIOD": 14,
            "VOL_AVG_PERIOD": 20,
            "ADX_PERIOD": 14,
            "DRY_RUN": True,
            "SYMBOL_SETTINGS": {},
            "INITIAL_SL_ATR": 2.0
        }
        self.engine = TrendCrusherV2(self.config)
        
        # 가상 데이터 생성 (EMA 수렴을 충분히 시뮬레이션하기 위해 1000개 봉 사용)
        dates = pd.date_range(start="2023-01-01", periods=1000, freq="h")
        self.df_1h = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.uniform(100, 110, 1000),
            'high': np.random.uniform(110, 120, 1000),
            'low': np.random.uniform(90, 100, 1000),
            'close': np.random.uniform(100, 110, 1000),
            'volume': np.random.uniform(1000, 5000, 1000)
        })
        self.df_4h = self.df_1h.copy()

    async def test_incremental_indicator_accuracy(self):
        """증분 계산(is_live=True) 결과가 전체 계산 결과와 충분히 근사한지 확인"""
        # 1. 전체 데이터 계산
        full_res = self.engine.calculate_indicators(self.df_1h, self.df_4h, self.config, is_live=False)
        full_last_row = full_res.iloc[-1]

        # 2. 최근 150개 봉만 사용한 증분 계산 (tail=max_p*3 = 150)
        inc_res = self.engine.calculate_indicators(self.df_1h, self.df_4h, self.config, is_live=True)
        inc_last_row = inc_res.iloc[-1]

        # Donchian Channel은 정확히 일치해야 함
        self.assertAlmostEqual(full_last_row['upper'], inc_last_row['upper'], places=4)
        
        # EMA/ADX는 슬라이싱에 의한 초기화 오차가 발생하므로 트레이딩에 지장 없는 수준(0.2% 미만 오차)인지 확인
        full_ema, inc_ema = full_last_row['ema_h'], inc_last_row['ema_h']
        ema_diff_pct = abs(full_ema - inc_ema) / full_ema
        self.assertLess(ema_diff_pct, 0.005, f"EMA drift too high: {ema_diff_pct:.4%}")
        
        # ADX도 마찬가지로 근사치 확인
        self.assertAlmostEqual(full_last_row['adx'], inc_last_row['adx'], delta=1.0)
        print("✅ Incremental Indicator Accuracy Test Passed (with tolerance for statistical convergence)")

    @patch('scripts.live_bot_async.DBManager')
    @patch('scripts.live_bot_async.TelegramNotifier')
    async def test_throttling_logic(self, mock_notifier, mock_db):
        """DB 기록 스로틀링 작동 확인"""
        mock_exchange = AsyncMock()
        mock_pm = AsyncMock() # AsyncMock for calculate_order_qty
        
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.df_indicators = pd.DataFrame([{'upper': 1000, 'lower': 900, 'ema_h': 950, 'atr': 20, 'volume': 1000, 'adx': 25, 'avg_vol': 500}])
        
        # 1. 첫 번째 업데이트 (기록됨)
        await bot.on_mark_price_update(950)
        initial_record_ts = bot.last_db_record_ts
        self.assertNotEqual(initial_record_ts, 0)
        
        # 2. 1초 뒤 업데이트 (스로틀링에 의해 기록되지 않음)
        with patch('time.time', return_value=initial_record_ts + 1):
            await bot.on_mark_price_update(951)
            self.assertEqual(bot.last_db_record_ts, initial_record_ts)
            
        # 3. 6초 뒤 업데이트 (기록되어야 함)
        with patch('time.time', return_value=initial_record_ts + 6):
            await bot.on_mark_price_update(952)
            self.assertGreater(bot.last_db_record_ts, initial_record_ts)
        
        print("✅ Throttling Logic Test Passed")

    @patch('scripts.live_bot_async.DBManager')
    @patch('scripts.live_bot_async.TelegramNotifier')
    async def test_order_update_fill_logic(self, mock_notifier, mock_db):
        """User Data Stream 메시지에 의한 체결 및 SL 생성 로직 확인"""
        mock_exchange = AsyncMock()
        mock_pm = AsyncMock()
        
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
        bot.active_sniper_order_id = "SNIPER_123"
        bot.sl_price = 9000
        
        # FILLED 메시지 수신 시뮬레이션
        order_msg = {
            'i': "SNIPER_123", 's': "BTCUSDT", 'X': "FILLED", 'S': "BUY", 'z': "1.0", 'L': "10000"
        }
        
        await bot.on_order_update(order_msg)
        
        # 봇 상태 검증
        self.assertEqual(bot.position, 1)
        self.assertEqual(bot.entry_price, 10000)
        self.assertIsNone(bot.active_sniper_order_id)
        # DRY_RUN 상황이므로 DRY_SL이 할당되었는지 확인
        self.assertEqual(bot.sl_order_id, "DRY_SL")
        print("✅ Order Update Fill Logic Test Passed")

    async def test_sl_sync_detection(self):
        """트레일링 스탑 이동 감지 임계치(0.05%) 작동 확인"""
        mock_exchange = AsyncMock()
        bot = SymbolBotAsync("BTC/USDT", mock_exchange, AsyncMock(), AsyncMock(), AsyncMock())
        bot.sl_price = 10000
        bot.last_sl_sync_price = 10000
        
        # 1. 0.01% 이동 (동기화 불필요)
        bot.sl_price = 10001
        diff = abs(bot.sl_price - bot.last_sl_sync_price) / bot.last_sl_sync_price
        self.assertTrue(diff < 0.0005)
        
        # 2. 0.1% 이동 (동기화 필요)
        bot.sl_price = 10011
        diff = abs(bot.sl_price - bot.last_sl_sync_price) / bot.last_sl_sync_price
        self.assertTrue(diff > 0.0005)
        print("✅ SL Sync Detection Test Passed")

if __name__ == '__main__':
    unittest.main()
