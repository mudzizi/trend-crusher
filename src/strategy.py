import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.config import CONFIG
from src.risk import calculate_position_size as shared_calculate_position_size

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
        self.last_entry_time = pd.Timestamp.min
        self.next_split_time = None
        self.splits_filled = 0
        self.trades = []
        self.equity_curve = []

    def calculate_position_size(self, price, stop_loss_price, risk_pct):
        return shared_calculate_position_size(
            capital=self.capital,
            price=price,
            stop_loss_price=stop_loss_price,
            risk_pct=risk_pct,
            max_leverage=self.c.get("MAX_LEVERAGE"),
            max_trade_loss_pct_cap=self.c.get("MAX_TRADE_LOSS_PCT_CAP"),
        )

    def run_precision_backtest(self, df_sig, df_trend, df_check, vol_mult=None, atr_trail_mult=None, risk_pct=None, ema_period=None):
        vol_mult = vol_mult if vol_mult is not None else self.c["VOL_MULTIPLIER"]
        atr_trail_mult = atr_trail_mult if atr_trail_mult is not None else self.c["TRAILING_ATR_MULT"]
        risk_pct = risk_pct if risk_pct is not None else self.c["RISK_PER_TRADE"]
        ema_period = ema_period if ema_period is not None else self.c["EMA_TREND_PERIOD"]

        df = df_sig.copy()
        df['upper'], df['lower'] = calculate_donchian(df, period=self.c["DONCHIAN_PERIOD"])
        df['atr'] = calculate_atr(df, period=14)
        df['avg_vol'] = calculate_avg_vol(df, period=20)
        
        ema_vals = calculate_ema(df_trend, period=ema_period)
        df_h = pd.DataFrame({'timestamp': df_trend['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df = df.join(df_h, on='timestamp').ffill()
        
        df_check_idx = df_check.set_index(pd.to_datetime(df_check['timestamp']))
        
        for i in range(max(self.c["DONCHIAN_PERIOD"], 1), len(df)):
            row = df.iloc[i]
            curr_time = pd.to_datetime(row['timestamp'])
            if curr_time not in df_check_idx.index: continue
            
            if self.position != 0:
                tf_delta = pd.to_timedelta(self.c["SIGNAL_TIMEFRAME"])
                next_bar = curr_time + tf_delta
                try: intra_data = df_check_idx.loc[curr_time : next_bar]
                except KeyError: intra_data = pd.DataFrame()

                closed = False
                for m_time, m_row in intra_data.iterrows():
                    m_close = m_row['close']
                    if self.position == 1:
                        self.max_price_seen = max(self.max_price_seen, m_close)
                        trail_sl = self.max_price_seen - (row['atr'] * atr_trail_mult)
                        if m_close <= trail_sl or m_close <= self.sl_price:
                            self._close_position(m_close, m_time); closed = True; break
                    else:
                        self.min_price_seen = min(self.min_price_seen, m_close)
                        trail_sl = self.min_price_seen + (row['atr'] * atr_trail_mult)
                        if m_close >= trail_sl or m_close >= self.sl_price:
                            self._close_position(m_close, m_time); closed = True; break
                if closed: continue

            is_vol_burst = row['volume'] > (row['avg_vol'] * vol_mult)
            signal_direction = 0
            if is_vol_burst and row['close'] > row['ema_h'] and row['close'] > row['upper']:
                signal_direction = 1
            elif is_vol_burst and row['close'] < row['ema_h'] and row['close'] < row['lower']:
                signal_direction = -1

            if self.position != 0 and self._can_add_split(curr_time, row):
                self._add_position_split(row['close'], curr_time, risk_pct)
            elif signal_direction != 0 and self.position == 0 and curr_time > self.last_close_time:
                self._open_position(signal_direction, row['close'], row['atr'], curr_time, risk_pct)

            self.equity_curve.append(self.capital)
        return self.trades, self.equity_curve

    def _open_position(self, direction, price, atr, timestamp, risk_pct):
        if direction == 1:
            self.sl_price = price - (atr * self.c["INITIAL_SL_ATR"])
        else:
            self.sl_price = price + (atr * self.c["INITIAL_SL_ATR"])
        self._apply_entry_fill(direction, price, timestamp, risk_pct, is_add=False)

    def _can_add_split(self, timestamp, row):
        max_splits = max(int(self.c.get("ENTRY_SPLIT_COUNT", 1)), 1)
        if self.position == 0 or self.splits_filled >= max_splits or self.next_split_time is None:
            return False
        if timestamp < self.next_split_time:
            return False
        if self.position == 1:
            return bool(row['close'] > row['ema_h'])
        return bool(row['close'] < row['ema_h'])

    def _add_position_split(self, price, timestamp, risk_pct):
        self._apply_entry_fill(self.position, price, timestamp, risk_pct, is_add=True)

    def _apply_entry_fill(self, direction, price, timestamp, risk_pct, is_add):
        split_count = max(int(self.c.get("ENTRY_SPLIT_COUNT", 1)), 1)
        split_risk_pct = risk_pct / split_count
        side = 'LONG' if direction == 1 else 'SHORT'
        fill_price = price * (1 + self.c["SLIPPAGE"]) if direction == 1 else price * (1 - self.c["SLIPPAGE"])
        fill_quantity = self.calculate_position_size(fill_price, self.sl_price, split_risk_pct)

        if fill_quantity <= 0:
            return

        fee = fill_price * fill_quantity * self.c["FEE_RATE"]
        existing_quantity = self.quantity
        new_total_quantity = existing_quantity + fill_quantity
        weighted_notional = (self.entry_price * existing_quantity) + (fill_price * fill_quantity)
        self.entry_price = weighted_notional / new_total_quantity
        self.quantity = new_total_quantity
        self.capital -= fee
        self.position = direction
        self.last_entry_time = timestamp
        self.splits_filled += 1
        if self.splits_filled < split_count:
            self.next_split_time = timestamp + pd.to_timedelta(self.c["SIGNAL_TIMEFRAME"])
        else:
            self.next_split_time = None
        self.max_price_seen = max(self.max_price_seen, fill_price) if existing_quantity > 0 else fill_price
        self.min_price_seen = min(self.min_price_seen, fill_price) if existing_quantity > 0 else fill_price

        if is_add and self.trades:
            self.trades[-1].update({'price': self.entry_price, 'quantity': self.quantity, 'splits_filled': self.splits_filled})
        else:
            self.trades.append({
                'time': timestamp,
                'type': 'OPEN',
                'side': side,
                'price': self.entry_price,
                'quantity': self.quantity,
                'splits_filled': self.splits_filled,
            })

    def _close_position(self, price, timestamp):
        exit_price = price
        pnl = (exit_price - self.entry_price) * self.quantity * self.position
        fee = exit_price * self.quantity * self.c["FEE_RATE"]
        net_change = pnl - fee

        cap_pct = self.c.get("MAX_TRADE_LOSS_PCT_CAP")
        cap_applied = False
        if cap_pct is not None and self.quantity > 0 and self.capital > 0:
            trade_capital_pct = (net_change / self.capital) * 100
            if trade_capital_pct < -float(cap_pct):
                target_net_change = -(self.capital * float(cap_pct) / 100)
                exit_price = self._solve_capped_exit_price(target_net_change)
                pnl = (exit_price - self.entry_price) * self.quantity * self.position
                fee = exit_price * self.quantity * self.c["FEE_RATE"]
                net_change = pnl - fee
                cap_applied = True

        self.capital += net_change
        self.trades.append({
            'time': timestamp,
            'type': 'CLOSE',
            'price': exit_price,
            'quantity': self.quantity,
            'splits_filled': self.splits_filled,
            'cap_applied': cap_applied,
        })
        self.position = 0
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.splits_filled = 0
        self.last_entry_time = pd.Timestamp.min
        self.next_split_time = None
        self.last_close_time = timestamp

    def _solve_capped_exit_price(self, target_net_change):
        if self.position == 1:
            return (self.entry_price + (target_net_change / self.quantity)) / (1 - self.c["FEE_RATE"])
        return (self.entry_price - (target_net_change / self.quantity)) / (1 + self.c["FEE_RATE"])
