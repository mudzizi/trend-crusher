import pandas as pd
import numpy as np
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG

def verify_indicators_locally():
    # 1. 샘플 데이터 로드 (TRUMP/USDT 1h)
    symbol = "TRUMP_USDT"
    data_path = f"data/{symbol}_1h.csv"
    
    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found.")
        return

    df = pd.read_csv(data_path).tail(100) # 최근 100개 봉 대상
    
    print(f"--- Indicator Verification for {symbol} ---")
    
    # 2. 지표 계산
    df['upper'], df['lower'] = calculate_donchian(df, period=20)
    df['ema_200'] = calculate_ema(df, period=200)
    df['atr_14'] = calculate_atr(df, period=14)
    df['adx_14'] = calculate_adx(df, period=14)
    
    # 3. 최신 5개 데이터 출력
    last_5 = df.tail(5)
    
    for i, row in last_5.iterrows():
        print(f"\n[Time: {row['timestamp']}]")
        print(f"  Close: {row['close']:.4f}")
        print(f"  EMA 200: {row['ema_200']:.4f}")
        print(f"  Donchian: Upper {row['upper']:.4f}, Lower {row['lower']:.4f}")
        print(f"  ATR 14: {row['atr_14']:.4f} ({(row['atr_14']/row['close'])*100:.2f}%)")
        print(f"  ADX 14: {row['adx_14']:.2f}")

    # 4. 상식적인 범위 체크
    print("\n--- Health Check ---")
    adx_val = df['adx_14'].iloc[-1]
    if 0 <= adx_val <= 100:
        print(f"✅ ADX is in valid range (0-100): {adx_val:.2f}")
    else:
        print(f"❌ ADX is INVALID: {adx_val:.2f}")
        
    atr_val = df['atr_14'].iloc[-1]
    if atr_val > 0:
        print(f"✅ ATR is positive: {atr_val:.4f}")
    else:
        print(f"❌ ATR is INVALID: {atr_val:.4f}")

if __name__ == "__main__":
    verify_indicators_locally()
