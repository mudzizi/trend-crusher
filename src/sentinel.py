import numpy as np
import pandas as pd

class MarketSentinel:
    """
    기존 전략의 외부에서 진입 허용 여부를 판단하고 
    시스템 전체를 중단(Kill Switch)시키는 독립 감시 엔진
    """
    def __init__(self, config=None):
        self.config = config or {}
        self.daily_loss_limit = self.config.get("SENTINEL_DAILY_LOSS_LIMIT", -5.0) # -5% 손실 시 차단
        self.chop_threshold = self.config.get("SENTINEL_CHOP_THRESHOLD", 61.8)    # 61.8 이상이면 횡보
        self.bb_width_threshold = self.config.get("SENTINEL_BB_WIDTH_MIN", 0.01) # 너무 좁으면 변동성 부족
        
        # 상태 저장 (Kill Switch용)
        self.is_killed = False
        self.kill_reason = ""

    def calculate_choppiness(self, df, period=14):
        """
        Choppiness Index 계산: 100 * log10( Sum(ATR(1)) / (MaxHigh - MinLow) ) / log10(period)
        0에 가까우면 강한 추세, 100에 가까우면 극심한 횡보
        """
        if len(df) < period: return 50.0
        
        tr1 = pd.DataFrame()
        tr1['h-l'] = df['high'] - df['low']
        tr1['h-pc'] = abs(df['high'] - df['close'].shift(1))
        tr1['l-pc'] = abs(df['low'] - df['close'].shift(1))
        tr = tr1.max(axis=1)
        
        atr_sum = tr.rolling(period).sum()
        max_h = df['high'].rolling(period).max()
        min_l = df['low'].rolling(period).min()
        
        chop = 100 * np.log10(atr_sum / (max_h - min_l + 1e-10)) / np.log10(period)
        return chop.fillna(50.0)

    def is_market_safe(self, row):
        """
        시장 상황(횡보 여부)에 따른 진입 허용 판단
        """
        # 1. Kill Switch 체크
        if self.is_killed:
            return False, f"KILL_SWITCH_ACTIVE: {self.kill_reason}"

        # 2. Choppiness Index 체크
        # row에 chop 데이터가 미리 계산되어 있다고 가정하거나 여기서 계산 로직 연동
        if 'chop' in row and row['chop'] > self.chop_threshold:
            return False, f"SIDEWAYS_CHOP ({row['chop']:.1f})"

        # 3. 추가적인 횡보 필터 (예: BB Width가 너무 좁은 경우 - 에너지 응축 전)
        # if 'bb_width' in row and row['bb_width'] < self.bb_width_threshold:
        #    return False, "LOW_VOLATILITY_SQUEEZE"

        return True, "SAFE"

    def check_kill_switch(self, daily_pnl_pct):
        """
        일일 손실률을 기반으로 전체 시스템 중단 여부 결정
        """
        if daily_pnl_pct <= self.daily_loss_limit:
            self.is_killed = True
            self.kill_reason = f"Daily Loss Limit Reached ({daily_pnl_pct:.2f}%)"
            return True
        return False

    def reset_kill_switch(self):
        self.is_killed = False
        self.kill_reason = ""
