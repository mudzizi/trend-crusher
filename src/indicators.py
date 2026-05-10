import pandas as pd
import numpy as np

def calculate_donchian(df, period=20):
    # 상단/하단 채널 자체의 값만 계산 (Shift(1)을 통해 전봉 기준 채널을 잡아야 실시간 돌파가 가능)
    # 현재 봉을 포함하지 않아야 '돌파(Breakout)' 지점이 정적인 수평선으로 고정됨.
    upper = df['high'].shift(1).rolling(window=period).max()
    lower = df['low'].shift(1).rolling(window=period).min()
    return upper, lower

def calculate_ema(df, period=200):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # ATR도 현재 봉의 변동성을 포함하지 않도록 shift(1) 하는 것이 정석이나, 
    # 통상적으로는 현재 봉의 TR까지 포함하여 계산함. 최적화 시점 로직 유지.
    return tr.rolling(window=period).mean()

def calculate_avg_vol(df, period=20):
    # 거래량 평균도 현재 봉을 제외한 이전 20개 봉 기준
    return df['volume'].rolling(window=period).mean().shift(1)

def calculate_adx(df, period=14):
    df = df.copy()
    
    # 1. DM (Directional Movement) 계산
    # UpMove = H_curr - H_prev
    # DownMove = L_prev - L_curr
    df['up_move'] = df['high'].diff()
    df['down_move'] = df['low'].shift(1) - df['low']
    
    # plus_dm: UpMove > DownMove 이고 UpMove > 0 이면 UpMove, 아니면 0
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    # minus_dm: DownMove > UpMove 이고 DownMove > 0 이면 DownMove, 아니면 0
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    # 2. TR (True Range) 계산
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 3. Smoothed TR, +DM, -DM 계산 (Wilder's Smoothing equivalent to EMA with alpha=1/period)
    # adjust=False와 span=(2*period - 1)을 사용하면 Wilder's Smoothing(alpha=1/period)과 동일한 효과를 냅니다.
    span_val = 2 * period - 1
    smoothed_tr = df['tr'].ewm(span=span_val, adjust=False).mean()
    smoothed_plus_dm = df['plus_dm'].ewm(span=span_val, adjust=False).mean()
    smoothed_minus_dm = df['minus_dm'].ewm(span=span_val, adjust=False).mean()
    
    # 4. DI (Directional Index) 계산
    plus_di = 100 * (smoothed_plus_dm / (smoothed_tr + 1e-10))
    minus_di = 100 * (smoothed_minus_dm / (smoothed_tr + 1e-10))
    
    # 5. DX 및 ADX 계산
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(span=span_val, adjust=False).mean()
    
    return adx
