import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx

def get_all_base_bars(df_1m, timeframe):
    df_1m = df_1m.copy()
    df_1m.set_index('timestamp', inplace=True)
    resampled = df_1m.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    return resampled.reset_index()

class TrendCrusherV2:
    def __init__(self, config):
        self.c = config
        self.capital = config.get("SEED", 10000)
        self.position = 0
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.trades = []
        self.equity_curve = []
        self.last_close_time = pd.Timestamp(0)

    def calculate_indicators(self, df_1h, df_4h, config):
        df = df_1h.copy()
        ema_period = config.get('EMA_TREND_PERIOD', 200)
        
        # Adaptive EMA: If we don't have enough 4h bars, reduce period
        if len(df_4h) < ema_period:
            new_period = max(10, len(df_4h) // 2)
            ema_values = calculate_ema(df_4h, new_period)
        else:
            ema_values = calculate_ema(df_4h, ema_period)
            
        # Create a temp series with 4h timestamps
        ema_s = pd.Series(ema_values.values, index=df_4h['timestamp'])
        
        df['upper'], df['lower'] = calculate_donchian(df, config.get('DONCHIAN_PERIOD', 20))
        # Reindex to 1h and ffill
        df['ema_h'] = ema_s.reindex(df['timestamp']).ffill().values
        
        df['atr'] = calculate_atr(df, config.get('ATR_PERIOD', 14))
        df['avg_vol'] = calculate_avg_vol(df, config.get('VOL_AVG_PERIOD', 20))
        df['adx'] = calculate_adx(df, config.get('ADX_PERIOD', 14))
        
        # Only drop rows where essential entry indicators are missing
        # Don't let EMA (Macro) kill all data if it's still warming up
        return df.dropna(subset=['upper', 'lower', 'atr', 'avg_vol', 'adx'])

    def _open_position(self, direction, price, sl, timestamp, risk_pct, is_sniper=False, is_maker=False):
        if self.position != 0: return
        effective_slippage = 0 if is_maker else (0.0001 if is_sniper else 0.0005)
        self.entry_price = price * (1 + (effective_slippage * direction))
        self.sl_price = sl
        self.quantity = self.calculate_position_size(self.entry_price, self.sl_price, risk_pct)
        if self.quantity > 0:
            self.position = direction
            self.max_price_seen = self.min_price_seen = self.entry_price
            self.trades.append({'time': timestamp, 'type': 'OPEN', 'side': 'LONG' if direction==1 else 'SHORT', 'price': self.entry_price})

    def _close_position(self, price, timestamp):
        if self.position == 0: return
        pnl = (price - self.entry_price) * self.quantity * self.position
        fee = price * self.quantity * 0.0005
        self.capital += (pnl - fee)
        self.trades.append({'time': timestamp, 'type': 'CLOSE', 'price': price, 'pnl_usdt': pnl - fee})
        self.position = 0
        self.last_close_time = timestamp

    def calculate_position_size(self, price, sl_price, risk_pct):
        risk_amt = self.capital * risk_pct
        stop_dist = abs(price - sl_price)
        return risk_amt / stop_dist if stop_dist > 0 else 0

    def check_entry_signal(self, row, last_price, use_sniper, retest_maker, config, is_ambushing=False):
        vol_m = config.get('VOL_MULTIPLIER', 2.0)
        adx_f = config.get('ADX_FILTER_LEVEL', 20)
        prox_p = config.get('SNIPER_PROXIMITY_PCT', 0.005)
        sl_atr = config.get('INITIAL_SL_ATR', 2.0)
        if is_ambushing: vol_m, adx_f, prox_p = vol_m * 0.8, adx_f * 0.8, prox_p * 2.0

        if row['volume'] < row['avg_vol'] * vol_m: return None, 0, 0
        if row['adx'] < adx_f: return None, 0, 0

        if last_price > row['ema_h']: # Long
            if last_price >= row['upper']: return 'MARKET', last_price, last_price - (row['atr'] * sl_atr)
            if use_sniper and last_price >= row['upper'] * (1 - prox_p): return 'SNIPER', row['upper'], row['upper'] - (row['atr'] * sl_atr)
            if retest_maker: return 'RETEST', row['upper'], row['upper'] - (row['atr'] * sl_atr)
        elif last_price < row['ema_h']: # Short
            if last_price <= row['lower']: return 'MARKET', last_price, last_price + (row['atr'] * sl_atr)
            if use_sniper and last_price <= row['lower'] * (1 + prox_p): return 'SNIPER', row['lower'], row['lower'] + (row['atr'] * sl_atr)
            if retest_maker: return 'RETEST', row['lower'], row['lower'] + (row['atr'] * sl_atr)
        return None, 0, 0

    def check_exit_signal(self, row, last_price, state, config):
        if state['position'] == 1:
            if last_price <= state['sl_price']: return True
            trail_sl = last_price - (row['atr'] * config.get('TRAILING_ATR_MULT', 3.0))
            if trail_sl > self.sl_price: self.sl_price = trail_sl
        else:
            if last_price >= state['sl_price']: return True
            trail_sl = last_price + (row['atr'] * config.get('TRAILING_ATR_MULT', 3.0))
            if trail_sl < self.sl_price: self.sl_price = trail_sl
        return False

    def run_streaming_backtest(self, df_1m, **kwargs):
        config = self.c.copy()
        config.update(kwargs)
        df_ind = kwargs.get('pre_calculated_ind')
        if df_ind is None:
            df_ind = self.calculate_indicators(get_all_base_bars(df_1m, "1h"), get_all_base_bars(df_1m, "4h"), config)
        
        # --- Crucial Fix: Standardize Timestamps to avoid matching errors ---
        m_times = pd.to_datetime(df_1m['timestamp']).values.astype('datetime64[m]')
        m_closes, m_highs, m_lows, m_vols = df_1m['close'].values, df_1m['high'].values, df_1m['low'].values, df_1m['volume'].values
        
        ind_shifted = df_ind.shift(1).copy()
        ind_times = pd.to_datetime(ind_shifted['timestamp']).values.astype('datetime64[m]')
        cols = ['upper', 'lower', 'ema_h', 'atr', 'avg_vol', 'adx']
        ind_arrs = {c: ind_shifted[c].values for c in cols}
        
        self.capital = config.get("SEED", 10000)
        self.trades, self.equity_curve, self.position = [], [self.capital], 0
        pending_maker = None
        
        use_sniper, retest_maker, risk_pct = config.get("USE_SNIPER", True), config.get("USE_RETEST_MAKER", False), config.get("RISK_PER_TRADE", 0.02)

        for i in range(len(df_1m)):
            curr_t = m_times[i]
            idx = np.searchsorted(ind_times, curr_t, side='right') - 1
            if idx < 0 or np.isnan(ind_arrs['upper'][idx]): continue
            
            row = {c: ind_arrs[c][idx] for c in cols}
            last_p = m_closes[i]
            
            if self.position != 0:
                if self.check_exit_signal(row, last_p, {'position': self.position, 'sl_price': self.sl_price}, config):
                    self._close_position(last_p, pd.Timestamp(curr_t))
            elif pending_maker:
                sig_type_h, _, _ = self.check_entry_signal(row, last_p, use_sniper, retest_maker, config, is_ambushing=True)
                if sig_type_h != 'RETEST': pending_maker = None
                elif (pending_maker['side'] == 1 and m_lows[i] <= pending_maker['price']) or \
                     (pending_maker['side'] == -1 and m_highs[i] >= pending_maker['price']):
                    self._open_position(pending_maker['side'], pending_maker['price'], pending_maker['sl'], pd.Timestamp(curr_t), risk_pct, is_maker=True)
                    pending_maker = None
            else:
                # Volume Reconstruction (Intra-bar)
                current_cum_vol = np.sum(m_vols[i - (i % 60) : i+1])
                live_row = row.copy(); live_row['volume'] = current_cum_vol
                sig_type, target_p, sl_p = self.check_entry_signal(live_row, last_p, use_sniper, retest_maker, config)
                
                if sig_type == 'RETEST': pending_maker = {'side': (1 if target_p > row['ema_h'] else -1), 'price': target_p, 'sl': sl_p}
                elif sig_type == 'SNIPER':
                    if (target_p > row['ema_h'] and m_highs[i] >= target_p) or (target_p < row['ema_h'] and m_lows[i] <= target_p):
                        self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_t), risk_pct, is_sniper=True)
                elif sig_type == 'MARKET':
                    self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_t), risk_pct)

            if i % 1440 == 0: self.equity_curve.append(self.capital)
        return self.trades, self.equity_curve, df_ind
