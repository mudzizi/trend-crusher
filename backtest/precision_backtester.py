import pandas as pd
import numpy as np
import os
from src.strategy import AggressiveVBOStrategy

def calculate_mdd(equity_curve):
    if not equity_curve: return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)

def run_precision_backtest():
    # 1. 데이터 로드 (신호용 1h, 검증용 1m)
    df_1h = pd.read_csv("data/ETH_USDT_1h.csv")
    df_4h = pd.read_csv("data/ETH_USDT_4h.csv")
    df_1m = pd.read_csv("data/ETH_USDT_1m.csv")
    
    # 1m 데이터를 타임스탬프 인덱스로 설정 (빠른 조회용)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_1m = df_1m.set_index('timestamp')
    
    # 전략 초기화 (리스크 2%)
    strategy = AggressiveVBOStrategy()
    risk_pct = 0.02
    atr_trail_mult = 3.5
    
    # 2. 신호 생성 (1h 봉 기준)
    # 기존 strategy.run 로직을 직접 구현하며 1m 검증 추가
    from src.indicators import calculate_donchian, calculate_ema, calculate_atr
    
    df = df_1h.copy()
    upper, lower = calculate_donchian(df, period=20)
    df['upper'] = upper.shift(1)
    df['lower'] = lower.shift(1)
    df['atr'] = calculate_atr(df, period=14)
    
    ema_4h = calculate_ema(df_4h, period=200)
    df_h = pd.DataFrame({'timestamp': df_4h['timestamp'], 'ema_4h': ema_4h}).set_index('timestamp')
    df = df.join(df_h, on='timestamp').ffill()
    
    capital = 10000
    initial_capital = 10000
    position = 0 # 1 or -1
    entry_price = 0
    quantity = 0
    sl_price = 0
    max_p = 0
    min_p = float('inf')
    last_close_time = pd.Timestamp.min
    trades = []
    equity_curve = []

    print("Starting Precision Backtest (1m Check)...")

    for i in range(1, len(df)):
        row = df.iloc[i]
        curr_time = pd.to_datetime(row['timestamp'])
        
        # --- 1m 검증: 포지션이 있을 때 ---
        if position != 0:
            # 해당 1시간(60분) 동안의 1분봉 데이터를 가져옴
            next_hour = curr_time + pd.Timedelta(hours=1)
            intra_data = df_1m.loc[curr_time : next_hour]
            
            closed_in_this_bar = False
            for m_time, m_row in intra_data.iterrows():
                m_close = m_row['close']
                
                # 고점/저점 갱신
                if position == 1:
                    max_p = max(max_p, m_close)
                    # 트레일링 조건 체크
                    pnl_pct = (m_close - entry_price) / entry_price
                    trail_sl = max_p - (row['atr'] * atr_trail_mult)
                    
                    if m_close <= trail_sl or m_close <= sl_price:
                        # 청산 실행 (1분 단위 정밀 청산)
                        pnl = (m_close - entry_price) * quantity * position
                        fee = m_close * quantity * 0.0004
                        capital += pnl - fee
                        position = 0
                        last_close_time = m_time
                        trades.append({'time': m_time, 'type': 'CLOSE', 'price': m_close})
                        closed_in_this_bar = True
                        break
                else:
                    min_p = min(min_p, m_close)
                    pnl_pct = (entry_price - m_close) / entry_price
                    trail_sl = min_p + (row['atr'] * atr_trail_mult)
                    
                    if m_close >= trail_sl or m_close >= sl_price:
                        pnl = (m_close - entry_price) * quantity * position
                        fee = m_close * quantity * 0.0004
                        capital += pnl - fee
                        position = 0
                        last_close_time = m_time
                        trades.append({'time': m_time, 'type': 'CLOSE', 'price': m_close})
                        closed_in_this_bar = True
                        break
            
            if closed_in_this_bar: continue

        # --- 진입 체크 (1h 신호) ---
        if position == 0 and curr_time > last_close_time:
            c_close = row['close']
            if c_close > row['ema_4h'] and c_close > row['upper']:
                sl_price = c_close - (row['atr'] * 2.0)
                # 수량 계산
                risk_amt = capital * risk_pct
                quantity = risk_amt / abs(c_close - sl_price)
                entry_price = c_close * (1 + 0.0005) # 슬리피지 포함
                capital -= entry_price * quantity * 0.0004 # 수수료
                position = 1
                max_p = entry_price
                trades.append({'time': curr_time, 'type': 'OPEN_LONG', 'price': entry_price})
            
            elif c_close < row['ema_4h'] and c_close < row['lower']:
                sl_price = c_close + (row['atr'] * 2.0)
                risk_amt = capital * risk_pct
                quantity = risk_amt / abs(c_close - sl_price)
                entry_price = c_close * (1 - 0.0005)
                capital -= entry_price * quantity * 0.0004
                position = -1
                min_p = entry_price
                trades.append({'time': curr_time, 'type': 'OPEN_SHORT', 'price': entry_price})

        equity_curve.append(capital)

    # 결과 리포트
    final_return = ((capital / initial_capital) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    print(f"\n[Precision Results (1m Check)]")
    print(f"Final Return: {final_return:.2f}%")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Total Trades: {len(trades)//2}")

if __name__ == "__main__":
    run_precision_backtest()
