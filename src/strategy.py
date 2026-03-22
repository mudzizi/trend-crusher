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

    @staticmethod
    def calculate_indicators(df_sig, df_trend, config=CONFIG):
        """
        Shared indicator calculation logic for both Backtest and Live.
        """
        df = df_sig.copy()
        df['upper'], df['lower'] = calculate_donchian(df, period=config.get("DONCHIAN_PERIOD", 20))
        df['atr'] = calculate_atr(df, period=config.get("ATR_PERIOD", 14))
        df['avg_vol'] = calculate_avg_vol(df, period=config.get("AVG_VOL_PERIOD", 20))
        df['adx'] = calculate_adx(df, period=config.get("ADX_PERIOD", 14))
        
        ema_vals = calculate_ema(df_trend, period=config.get("EMA_TREND_PERIOD", 200))
        df_h = pd.DataFrame({'timestamp': df_trend['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df = df.join(df_h, on='timestamp').ffill()
        return df

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None):
        """
        Logic to determine if a new position should be opened.
        Returns: (signal_type, price, sl_price) or (None, None, None)
        signal_type: 'MARKET', 'SNIPER', 'RETEST'
        """
        c = config if config else self.c
        vol_mult = c.get("VOL_MULTIPLIER", 2.0)
        adx_threshold = c.get("ADX_FILTER_LEVEL", 25.0)
        initial_sl_atr = c.get("INITIAL_SL_ATR", 2.0)

        is_vol_burst = row['volume'] > (row['avg_vol'] * vol_mult)
        is_trending = row['adx'] > adx_threshold
        
        if not (is_vol_burst and is_trending):
            return None, None, None

        if retest_maker:
            if last_price > row['ema_h'] and last_price > row['upper']:
                sl = row['upper'] - (row['atr'] * initial_sl_atr)
                return 'RETEST', row['upper'], sl
            elif last_price < row['ema_h'] and last_price < row['lower']:
                sl = row['lower'] + (row['atr'] * initial_sl_atr)
                return 'RETEST', row['lower'], sl
        
        elif use_sniper:
            prox_threshold = c.get("SNIPER_PROXIMITY_PCT", 0.005)
            dist_top = abs(last_price - row['upper']) / (last_price + 1e-10)
            dist_bottom = abs(last_price - row['lower']) / (last_price + 1e-10)

            if last_price > row['ema_h'] and dist_top <= prox_threshold:
                sl = row['upper'] - (row['atr'] * initial_sl_atr)
                return 'SNIPER', row['upper'], sl
            elif last_price < row['ema_h'] and dist_bottom <= prox_threshold:
                sl = row['lower'] + (row['atr'] * initial_sl_atr)
                return 'SNIPER', row['lower'], sl
        
        else:
            # Market (Close-based)
            if last_price > row['ema_h'] and last_price > row['upper']:
                sl = last_price - (row['atr'] * initial_sl_atr)
                return 'MARKET', last_price, sl
            elif last_price < row['ema_h'] and last_price < row['lower']:
                sl = last_price + (row['atr'] * initial_sl_atr)
                return 'MARKET', last_price, sl
        
        return None, None, None

    def check_exit_signal(self, row, last_price, state, config=None):
        """
        Logic to determine if an existing position should be closed.
        state: {'position', 'entry_price', 'max_price_seen', 'min_price_seen', 'sl_price'}
        Returns: True if should close, False otherwise.
        """
        c = config if config else self.c
        atr_trail_mult = c.get("TRAILING_ATR_MULT", 3.0)
        use_adaptive = c.get("USE_ADAPTIVE_TRAIL", False)
        adaptive_steps = c.get("ADAPTIVE_TRAIL_STEPS", [])

        curr_atr_mult = atr_trail_mult
        pnl_pct = ((last_price / state['entry_price']) - 1) * 100 * state['position']

        if use_adaptive:
            for step in adaptive_steps:
                if pnl_pct >= step['pnl_pct']:
                    if 'tighten_ratio' in step:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * step['tighten_ratio'])
                    elif 'atr_mult' in step:
                        curr_atr_mult = min(curr_atr_mult, step['atr_mult'])

        if state['position'] == 1:
            trail_sl = state['max_price_seen'] - (row['atr'] * curr_atr_mult)
            if last_price <= trail_sl or last_price <= state['sl_price']:
                return True
        elif state['position'] == -1:
            trail_sl = state['min_price_seen'] + (row['atr'] * curr_atr_mult)
            if last_price >= trail_sl or last_price >= state['sl_price']:
                return True
        
        return False

    def calculate_position_size(self, price, stop_loss_price, risk_pct):
        risk_amt = self.capital * risk_pct
        stop_dist = abs(price - stop_loss_price)
        return risk_amt / stop_dist if stop_dist > 0 else 0

    def run_precision_backtest(self, df_sig, df_trend, df_check, **kwargs):
        """
        Backtest runner using the modular signal/exit logic.
        """
        config = self.c.copy()
        
        # Map lowercase optimizer-style kwargs to uppercase config keys
        mapping = {
            'vol_mult': 'VOL_MULTIPLIER',
            'atr_trail_mult': 'TRAILING_ATR_MULT',
            'risk_pct': 'RISK_PER_TRADE',
            'ema_period': 'EMA_TREND_PERIOD',
            'adx_threshold': 'ADX_FILTER_LEVEL',
            'donchian_period': 'DONCHIAN_PERIOD'
        }
        for kw, cfg_key in mapping.items():
            if kw in kwargs:
                config[cfg_key] = kwargs[kw]
        
        # Any other kwargs can also overwrite config if they match keys
        for kw, val in kwargs.items():
            if kw.upper() in config:
                config[kw.upper()] = val

        df = self.calculate_indicators(df_sig, df_trend, config)
        df_check_idx = df_check.set_index(pd.to_datetime(df_check['timestamp']))
        
        pending_maker_order = None # {side, price, sl, atr, timestamp}
        use_sniper = kwargs.get('use_sniper', False)
        retest_maker = kwargs.get('retest_maker', False)
        risk_pct = config.get("RISK_PER_TRADE", 0.02)

        for i in range(max(config.get("DONCHIAN_PERIOD", 20), 1), len(df)):
            row = df.iloc[i]
            curr_time = pd.to_datetime(row['timestamp'])
            if curr_time not in df_check_idx.index: continue
            
            # 1. Position Management
            if self.position != 0:
                tf_delta = pd.to_timedelta(config["SIGNAL_TIMEFRAME"])
                intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]

                closed = False
                for m_time, m_row in intra_data.iterrows():
                    state = {
                        'position': self.position,
                        'entry_price': self.entry_price,
                        'max_price_seen': self.max_price_seen,
                        'min_price_seen': self.min_price_seen,
                        'sl_price': self.sl_price
                    }
                    if self.check_exit_signal(row, m_row['close'], state, config):
                        self._close_position(m_row['close'], m_time)
                        closed = True
                        break
                    
                    # Update extreme prices during intra-bar
                    if self.position == 1: self.max_price_seen = max(self.max_price_seen, m_row['close'])
                    else: self.min_price_seen = min(self.min_price_seen, m_row['close'])
                
                if closed: continue

            # 2. Check Pending Retest Maker Order
            if pending_maker_order and self.position == 0:
                tf_delta = pd.to_timedelta(config["SIGNAL_TIMEFRAME"])
                intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                
                for m_time, m_row in intra_data.iterrows():
                    if pending_maker_order['side'] == 1:
                        if m_row['low'] <= pending_maker_order['price']:
                            self._open_position(1, pending_maker_order['price'], pending_maker_order['sl'], m_time, risk_pct, is_maker=True)
                            pending_maker_order = None; break
                    else:
                        if m_row['high'] >= pending_maker_order['price']:
                            self._open_position(-1, pending_maker_order['price'], pending_maker_order['sl'], m_time, risk_pct, is_maker=True)
                            pending_maker_order = None; break
                
                if pending_maker_order and (curr_time - pending_maker_order['timestamp']).total_seconds() > 14400:
                    pending_maker_order = None

            # 3. New Signal Discovery
            if self.position == 0 and not pending_maker_order and curr_time > self.last_close_time:
                sig_type, target_p, sl_p = self.check_entry_signal(row, row['close'], use_sniper, retest_maker, config)
                
                if sig_type == 'RETEST':
                    pending_maker_order = {'side': (1 if target_p > row['ema_h'] else -1), 'price': target_p, 'sl': sl_p, 'timestamp': curr_time}
                elif sig_type == 'SNIPER':
                    tf_delta = pd.to_timedelta(config["SIGNAL_TIMEFRAME"])
                    intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                    for m_time, m_row in intra_data.iterrows():
                        if (target_p > row['ema_h'] and m_row['high'] >= target_p) or (target_p < row['ema_h'] and m_row['low'] <= target_p):
                            self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, m_time, risk_pct, is_sniper=True)
                            break
                elif sig_type == 'MARKET':
                    self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, curr_time, risk_pct)

            self.equity_curve.append(self.capital)
        return self.trades, self.equity_curve

    def _open_position(self, direction, price, sl_price, timestamp, risk_pct, is_sniper=False, is_maker=False):
        side = 'LONG' if direction == 1 else 'SHORT'
        current_fee_rate = 0.0002 if is_maker else 0.0005
        effective_slippage = 0 if is_maker else (0.0001 if is_sniper else 0.0005)
        
        self.entry_price = price * (1 + (effective_slippage * direction))
        self.sl_price = sl_price
        self.quantity = self.calculate_position_size(self.entry_price, self.sl_price, risk_pct)
        
        if self.quantity > 0:
            self.capital -= self.entry_price * self.quantity * current_fee_rate
            self.position = direction
            self.max_price_seen = self.entry_price
            self.min_price_seen = self.entry_price
            self.trades.append({'time': timestamp, 'type': 'OPEN', 'side': side, 'price': self.entry_price, 'qty': self.quantity, 'is_maker': is_maker})

    def _close_position(self, price, timestamp):
        taker_fee = 0.0005
        pnl = (price - self.entry_price) * self.quantity * self.position
        fee = price * self.quantity * taker_fee
        actual_pnl_usdt = pnl - fee
        self.capital += actual_pnl_usdt
        self.trades.append({'time': timestamp, 'type': 'CLOSE', 'price': price, 'pnl_usdt': actual_pnl_usdt})
        self.position = 0
        self.last_close_time = timestamp

