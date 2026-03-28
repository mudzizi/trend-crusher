import pandas as pd
import numpy as np

def calculate_donchian(df, period=20):
    # 상단/하단 채널 자체의 값만 계산 (Shift는 전략 레벨에서 결정)
    upper = df['high'].rolling(window=period).max()
    lower = df['low'].rolling(window=period).min()
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
    df['up_move'] = df['high'].diff()
    df['down_move'] = df['low'].diff().abs()
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (df['plus_dm'].rolling(window=period).mean() / (atr + 1e-10))
    minus_di = 100 * (df['minus_dm'].rolling(window=period).mean() / (atr + 1e-10))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    return dx.rolling(window=period).mean()
