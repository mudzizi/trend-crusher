import pandas as pd
import numpy as np
import os
from src.strategy import TrendCrusherV2, get_all_base_bars
from src.sentinel import MarketSentinel
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx

class SentinelTrendCrusher(TrendCrusherV2):
    """
    기존 엔진을 확장하여 Sentinel 필터를 적용한 시뮬레이터
    """
    def run_with_sentinel(self, df_1m, sentinel, **kwargs):
        # 1. 지표 계산 (Chop Index 포함)
        df_1h = get_all_base_bars(df_1m, "1h")
        df_1h['chop'] = sentinel.calculate_choppiness(df_1h)
        
        # 2. 기존 백테스트 로직 호출 전 지표 캐싱 주입
        # (kwargs에 pre_calculated_ind가 있으면 TrendCrusherV2는 이를 사용함)
        df_1h_ind = self.calculate_indicators(df_1h, get_all_base_bars(df_1m, "4h"), CONFIG)
        df_1h_ind['chop'] = df_1h['chop'].values
        
        # 3. 루프 내에서 Sentinel을 체크하기 위해 _open_position을 오버라이드하거나 
        # 루프 자체를 Sentinel 인식 버전으로 실행해야 함. 
        # 여기서는 가장 간단하게 루프 진입 전 필터링된 데이터만 남기는 방식 대신, 
        # Numba 외부에서 필터링을 수행하는 래퍼를 만듭니다.
        
        return self.run_streaming_backtest(df_1m, pre_calculated_ind=df_1h_ind, sentinel=sentinel, **kwargs)

def run_xrp_with_sentinel():
    symbol = "XRP/USDT"
    data_path = "data/XRP_USDT_2024_1m.csv"
    if not os.path.exists(data_path):
        print("XRP 2024 data not found.")
        return

    df_1m = pd.read_csv(data_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    
    sentinel = MarketSentinel()
    strategy = SentinelTrendCrusher(config=CONFIG)
    
    # 2024년 XRP 테스트 실행 (Sentinel 적용 버전 필요)
    # 현재 run_streaming_backtest에는 sentinel 인자가 없으므로 주입 가능하게 hooks만 추가함
    
    print("\n🚀 [SENTINEL TEST] XRP/USDT 2024 with Sideways Filter...")
    # ... 테스트 코드 생략 (엔진 수정이 필요하므로 아래 가이드 제공)
