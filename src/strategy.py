import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG

class TrendCrusherV2:
    def __init__(self, config=CONFIG):
        self.c = config
        self.capital = self.c["SEED"]
        self.initial_capital = self.c["SEED"]
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.last_close_time = pd.Timestamp.min
        self.trades = []
        self.equity_curve = []

    def calculate_position_size(self, price, stop_loss_price, risk_pct):
        risk_amt = self.capital * risk_pct
        stop_dist = abs(price - stop_loss_price)
        return risk_amt / stop_dist if stop_dist > 0 else 0

    def run_precision_backtest(self, df_sig, df_trend, df_check, vol_mult=None, atr_trail_mult=None, risk_pct=None, ema_period=None):
        vol_mult = vol_mult if vol_mult is not None else self.c["VOL_MULTIPLIER"]
        atr_trail_mult = atr_trail_mult if atr_trail_mult is not None else self.c["TRAILING_ATR_MULT"]
        risk_pct = risk_pct if risk_pct is not None else self.c["RISK_PER_TRADE"]
        ema_period = ema_period if ema_period is not None else self.c["EMA_TREND_PERIOD"]

        df = df_sig.copy()
        df['upper'], df['lower'] = calculate_donchian(df, period=self.c["DONCHIAN_PERIOD"])
        df['atr'] = calculate_atr(df, period=14)
        df['avg_vol'] = calculate_avg_vol(df, period=20)
        df['adx'] = calculate_adx(df, period=14)
        
        ema_vals = calculate_ema(df_trend, period=ema_period)
        df_h = pd.DataFrame({'timestamp': df_trend['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df = df.join(df_h, on='timestamp').ffill()
        
        df_check_idx = df_check.set_index(pd.to_datetime(df_check['timestamp']))
        
        for i in range(max(self.c["DONCHIAN_PERIOD"], 1), len(df)):
            row = df.iloc[i]
            curr_time = pd.to_datetime(row['timestamp'])
            if curr_time not in df_check_idx.index: continue
            
            if self.position != 0:
                # (중략 - 포지션 관리 로직)
                tf_delta = pd.to_timedelta(self.c["SIGNAL_TIMEFRAME"])
                next_bar = curr_time + tf_delta
                try: intra_data = df_check_idx.loc[curr_time : next_bar]
                except KeyError: intra_data = pd.DataFrame()

                closed = False
                for m_time, m_row in intra_data.iterrows():
                    m_close = m_row['close']
                    
                    # 1. Adaptive Trailing Stop Mult calculation
                    curr_atr_mult = atr_trail_mult
                    if self.c.get("USE_ADAPTIVE_TRAIL", False):
                        pnl_pct = ((m_close / self.entry_price) - 1) * 100 * self.position
                        for step in self.c.get("ADAPTIVE_TRAIL_STEPS", []):
                            if pnl_pct >= step['pnl_pct']:
                                curr_atr_mult = min(curr_atr_mult, step['atr_mult'])

                    # 2. Trailing Stop / SL Check
                    if self.position == 1:
                        self.max_price_seen = max(self.max_price_seen, m_close)
                        trail_sl = self.max_price_seen - (row['atr'] * curr_atr_mult)
                        if m_close <= trail_sl or m_close <= self.sl_price:
                            self._close_position(m_close, m_time); closed = True; break
                    else:
                        self.min_price_seen = min(self.min_price_seen, m_close)
                        trail_sl = self.min_price_seen + (row['atr'] * curr_atr_mult)
                        if m_close >= trail_sl or m_close >= self.sl_price:
                            self._close_position(m_close, m_time); closed = True; break
                if closed: continue

            if self.position == 0 and curr_time > self.last_close_time:
                is_vol_burst = row['volume'] > (row['avg_vol'] * vol_mult)
                is_trending = row['adx'] > self.c["ADX_FILTER_LEVEL"]

                if is_vol_burst and is_trending and row['close'] > row['ema_h'] and row['close'] > row['upper']:
                    self._open_position(1, row['close'], row['atr'], curr_time, risk_pct)
                elif is_vol_burst and is_trending and row['close'] < row['ema_h'] and row['close'] < row['lower']:
                    self._open_position(-1, row['close'], row['atr'], curr_time, risk_pct)

            self.equity_curve.append(self.capital)
        return self.trades, self.equity_curve

    def _open_position(self, direction, price, atr, timestamp, risk_pct):
        side = 'LONG' if direction == 1 else 'SHORT'
        if direction == 1:
            self.sl_price = price - (atr * self.c["INITIAL_SL_ATR"])
            self.entry_price = price * (1 + self.c["SLIPPAGE"])
        else:
            self.sl_price = price + (atr * self.c["INITIAL_SL_ATR"])
            self.entry_price = price * (1 - self.c["SLIPPAGE"])
        
        self.quantity = self.calculate_position_size(self.entry_price, self.sl_price, risk_pct)
        if self.quantity > 0:
            self.capital -= self.entry_price * self.quantity * self.c["FEE_RATE"]
            self.position = direction
            self.max_price_seen = self.entry_price
            self.min_price_seen = self.entry_price
            self.trades.append({
                'time': timestamp, 
                'type': 'OPEN', 
                'side': side, 
                'price': self.entry_price,
                'qty': self.quantity
            })

    def _close_position(self, price, timestamp):
        pnl = (price - self.entry_price) * self.quantity * self.position
        fee = price * self.quantity * self.c["FEE_RATE"]
        actual_pnl_usdt = pnl - fee
        self.capital += actual_pnl_usdt
        self.trades.append({
            'time': timestamp, 
            'type': 'CLOSE', 
            'price': price,
            'pnl_usdt': actual_pnl_usdt
        })
        self.position = 0
        self.last_close_time = timestamp
