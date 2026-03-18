import pandas as pd
import numpy as np
import os
from src.indicators import calculate_ema

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_mtf_precision_test(timeframe='1h', vol_mult=1.5):
    df_signal = pd.read_csv(f"data/ETH_USDT_{timeframe}.csv")
    df_4h = pd.read_csv("data/ETH_USDT_4h.csv")
    df_1m = pd.read_csv("data/ETH_USDT_1m.csv")
    
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m = df_1m.set_index('timestamp')
    
    df = df_signal.copy()
    df['upper'] = df['high'].rolling(window=20).max().shift(1)
    df['lower'] = df['low'].rolling(window=20).min().shift(1)
    df['avg_vol'] = df['volume'].rolling(window=20).mean().shift(1)
    
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    df['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(window=14).mean()
    
    ema_4h = calculate_ema(df_4h, period=200)
    df_h = pd.DataFrame({'timestamp': df_4h['timestamp'], 'ema_4h': ema_4h}).set_index('timestamp')
    df = df.join(df_h, on='timestamp').ffill()
    
    capital = 10000
    initial_capital = 10000
    position = 0
    entry_price = 0
    quantity = 0
    sl_price = 0
    max_p = 0
    min_p = float('inf')
    last_close_time = pd.Timestamp.min
    trades_count = 0
    equity_curve = []
    
    risk_pct = 0.02
    atr_trail_mult = 3.5
    
    if timeframe == '15m': tf_delta = pd.Timedelta(minutes=15)
    elif timeframe == '30m': tf_delta = pd.Timedelta(minutes=30)
    else: tf_delta = pd.Timedelta(hours=1)

    for i in range(20, len(df)):
        row = df.iloc[i]
        curr_time = pd.to_datetime(row['timestamp'])
        if curr_time not in df_1m.index: continue
        
        if position != 0:
            next_bar_time = curr_time + tf_delta
            try: intra_data = df_1m.loc[curr_time : next_bar_time]
            except KeyError: intra_data = pd.DataFrame()

            closed_in_bar = False
            for m_time, m_row in intra_data.iterrows():
                m_close = m_row['close']
                if position == 1:
                    max_p = max(max_p, m_close)
                    trail_sl = max_p - (row['atr'] * atr_trail_mult)
                    if m_close <= trail_sl or m_close <= sl_price:
                        capital += (m_close - entry_price) * quantity - (m_close * quantity * 0.0004)
                        position = 0; last_close_time = m_time; trades_count += 1
                        closed_in_bar = True; break
                else:
                    min_p = min(min_p, m_close)
                    trail_sl = min_p + (row['atr'] * atr_trail_mult)
                    if m_close >= trail_sl or m_close >= sl_price:
                        capital += (entry_price - m_close) * quantity - (m_close * quantity * 0.0004)
                        position = 0; last_close_time = m_time; trades_count += 1
                        closed_in_bar = True; break
            if closed_in_bar: continue

        # --- Entry Check with Volume Filter ---
        if position == 0 and curr_time > last_close_time:
            c_close = row['close']
            c_vol = row['volume']
            is_vol_burst = c_vol > (row['avg_vol'] * vol_mult)
            
            if is_vol_burst and c_close > row['ema_4h'] and c_close > row['upper']:
                sl_price = c_close - (row['atr'] * 2.0)
                if abs(c_close - sl_price) > 0:
                    quantity = (capital * risk_pct) / abs(c_close - sl_price)
                    entry_price = c_close * 1.0005
                    capital -= entry_price * quantity * 0.0004
                    position = 1; max_p = entry_price
            elif is_vol_burst and c_close < row['ema_4h'] and c_close < row['lower']:
                sl_price = c_close + (row['atr'] * 2.0)
                if abs(c_close - sl_price) > 0:
                    quantity = (capital * risk_pct) / abs(c_close - sl_price)
                    entry_price = c_close * 0.9995
                    capital -= entry_price * quantity * 0.0004
                    position = -1; min_p = entry_price
        
        equity_curve.append(capital)

    return {
        'Timeframe': timeframe,
        'Return (%)': round(((capital/initial_capital)-1)*100, 2),
        'MDD (%)': round(calculate_mdd(equity_curve)*100, 2),
        'Trades': trades_count
    }

if __name__ == "__main__":
    for mult in [1.0, 1.5, 2.0]: # 거래량 필터 배수별 테스트
        results = []
        print(f"\n--- Testing with Volume Multiplier: {mult} ---")
        for tf in ['15m', '30m', '1h']:
            results.append(run_mtf_precision_test(tf, vol_mult=mult))
        print(pd.DataFrame(results).to_string(index=False))
