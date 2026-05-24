import pandas as pd
import numpy as np
from numba import njit
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx, calculate_choppiness, calculate_chaos_index, calculate_squeeze_score
from src.config import CONFIG

@njit
def numba_check_entry(last_price, ema_h, upper, lower, atr, adx, avg_vol, volume, 
                      vol_mult, adx_threshold, initial_sl_atr, 
                      use_sniper, retest_maker, prox_threshold, is_ambushing=False,
                      fixed_sl_pct=0.0, adx_4h=0.0, adx_4h_threshold=20.0,
                      chop=50.0, ema_slope=0.0, chaos=20.0, squeeze=0.0):
    # --- V7.0 Momentum Chaos Engine ---
    
    # 1. Chaos Spike Filter (Based on 'Lucky Error')
    if chaos < 15: return 0, 0.0, 0.0

    # 2. Squeeze Breakout 
    v_mult_final = vol_mult
    if squeeze > 0: # Recently squeezed
        v_mult_final *= 0.7 
        
    # 3. Standard & MTF Filters
    if volume <= (avg_vol * v_mult_final) or adx_4h < adx_4h_threshold:
        return 0, 0.0, 0.0

    is_long = last_price > ema_h
    
    if retest_maker:
        if is_long and last_price > upper:
            sl = upper * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else upper - (atr * initial_sl_atr)
            return 3, upper, sl
        elif not is_long and last_price < lower:
            sl = lower * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else lower + (atr * initial_sl_atr)
            return 3, lower, sl
    
    elif use_sniper:
        dist_top = (upper - last_price) / (last_price + 1e-10) if last_price < upper else -1.0
        dist_bottom = (last_price - lower) / (last_price + 1e-10) if last_price > lower else -1.0

        if is_long and 0.0003 <= dist_top <= (prox_threshold + 1e-6):
            sl = upper * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else upper - (atr * initial_sl_atr)
            return 2, upper, sl
        elif not is_long and 0.0003 <= dist_bottom <= (prox_threshold + 1e-6):
            sl = lower * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else lower + (atr * initial_sl_atr)
            return 2, lower, sl
        
        if is_long and last_price >= (upper * 0.9997):
            sl = last_price * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else last_price - (atr * initial_sl_atr)
            return 1, last_price, sl
        elif not is_long and last_price <= (lower * 1.0003):
            sl = last_price * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else last_price + (atr * initial_sl_atr)
            return 1, last_price, sl
    
    else:
        if is_long and last_price > upper and ema_slope > 0:
            sl = last_price * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else last_price - (atr * initial_sl_atr)
            return 1, last_price, sl
        elif not is_long and last_price < lower and ema_slope < 0:
            sl = last_price * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else last_price + (atr * initial_sl_atr)
            return 1, last_price, sl
            
    return 0, 0.0, 0.0

@njit
def numba_check_exit(last_price, position, entry_price, max_price_seen, min_price_seen, sl_price, 
                     atr, atr_trail_mult, use_adaptive, adaptive_steps_arr, be_guard_threshold=0.0):
    curr_atr_mult = atr_trail_mult
    pnl_pct = ((last_price / entry_price) - 1) * 100 * position

    # 1. Break-even Guard
    if be_guard_threshold > 0 and pnl_pct >= be_guard_threshold:
        be_sl = entry_price * (1 + 0.001 * position)
        if position == 1:
            sl_price = max(sl_price, be_sl)
        else:
            sl_price = min(sl_price, be_sl) if sl_price > 0 else be_sl

    if use_adaptive:
        for i in range(len(adaptive_steps_arr)):
            step_pnl = adaptive_steps_arr[i, 0]
            step_tighten = adaptive_steps_arr[i, 1]
            if pnl_pct >= step_pnl:
                curr_atr_mult = min(curr_atr_mult, atr_trail_mult * step_tighten)

    if position == 1:
        trail_sl = max_price_seen - (atr * curr_atr_mult)
        if last_price <= trail_sl or last_price <= sl_price: return True
    elif position == -1:
        trail_sl = min_price_seen + (atr * curr_atr_mult)
        if last_price >= trail_sl or (sl_price > 0 and last_price >= sl_price): return True
    return False

@njit
def numba_find_first_exit(closes, lookup_indices, position, entry_price, initial_max, initial_min, initial_sl,
                          atrs, atr_trail_mult, use_adaptive, adaptive_steps_arr, be_guard_threshold=0.0):
    max_p = initial_max
    min_p = initial_min
    sl_p = initial_sl
    
    for i in range(len(closes)):
        idx = lookup_indices[i]
        if idx == -1: continue 
        
        last_p = closes[i]
        atr = atrs[idx]
        pnl_pct = ((last_p / entry_price) - 1) * 100 * position

        if be_guard_threshold > 0 and pnl_pct >= be_guard_threshold:
            be_sl = entry_price * (1 + 0.001 * position)
            if position == 1:
                sl_p = max(sl_p, be_sl)
            else:
                sl_p = min(sl_p, be_sl) if sl_p > 0 else be_sl

        if position == 1:
            max_p = max(max_p, last_p)
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            
            trail_sl = max_p - (atr * curr_atr_mult)
            if last_p <= trail_sl or last_p <= sl_p:
                return i, max_p, min_p
        else:
            min_p = min(min_p, last_p)
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            
            trail_sl = min_p + (atr * curr_atr_mult)
            if last_p >= trail_sl or (sl_p > 0 and last_p >= sl_p):
                return i, max_p, min_p
                
    return -1, max_p, min_p

def get_all_base_bars(df_1m, timeframe, include_incomplete=False):
    df_1m = df_1m.copy()
    df_1m.set_index('timestamp', inplace=True)
    resampled = df_1m.resample(timeframe).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    })
    if not include_incomplete:
        resampled = resampled.dropna()
    return resampled.reset_index()

class TrendCrusherV2:
    def __init__(self, config=CONFIG):
        self.c = config
        self.capital = config.get("SEED", 10000)
        self.position, self.entry_price, self.quantity = 0, 0, 0
        self.max_price_seen, self.min_price_seen = 0, 0
        self.sl_price = 0
        self.last_close_time = pd.Timestamp(0)
        self.trades, self.equity_curve = [], [self.capital]

    def calculate_indicators(self, df_sig, df_trend, config, is_live=False):
        df = df_sig.copy()
        if 'timestamp' not in df.columns: df = df.reset_index()
            
        df['upper'], df['lower'] = calculate_donchian(df, period=config.get("DONCHIAN_PERIOD", 20))
        df['atr'] = calculate_atr(df, period=config.get("ATR_PERIOD", 14))
        df['avg_vol'] = calculate_avg_vol(df, period=config.get("AVG_VOL_PERIOD", 20))
        df['adx'] = calculate_adx(df, period=config.get("ADX_PERIOD", 14))
        df['chop'] = calculate_choppiness(df, period=14)
        df['chaos'] = calculate_chaos_index(df, period=14)
        df['squeeze'] = calculate_squeeze_score(df)
        
        ema_period = config.get("EMA_TREND_PERIOD", 50)
        df['ema_h'] = calculate_ema(df, period=ema_period * 4)
        df['ema_slope'] = df['ema_h'].diff(3)
        
        df_4h = df_trend.copy()
        df_4h['adx_4h'] = calculate_adx(df_4h, period=config.get("ADX_PERIOD", 14))
        df = df.merge(df_4h[['timestamp', 'adx_4h']], on='timestamp', how='left').ffill().fillna(0.0)
        
        if 'timestamp' in df.columns: df = df.set_index('timestamp')
        return df

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None, is_ambushing=False):
        c = config if config else self.c
        sig_idx, target_p, sl_p = numba_check_entry(
            last_price, row['ema_h'], row['upper'], row['lower'], row['atr'], row['adx'], row['avg_vol'], row['volume'],
            c.get("VOL_MULTIPLIER", 2.0), c.get("ADX_FILTER_LEVEL", 25.0), c.get("INITIAL_SL_ATR", 2.0),
            use_sniper, retest_maker, c.get("SNIPER_PROXIMITY_PCT", 0.005), is_ambushing,
            fixed_sl_pct=c.get("INITIAL_SL_PCT", 0.0), adx_4h=row.get('adx_4h', 0.0), adx_4h_threshold=c.get("ADX_4H_THRESHOLD", 20.0),
            chop=row.get('chop', 50.0), ema_slope=row.get('ema_slope', 0.0),
            chaos=row.get('chaos', 20.0), squeeze=row.get('squeeze', 0.0)
        )
        sig_map = {0: None, 1: 'MARKET', 2: 'SNIPER', 3: 'RETEST'}
        return sig_map[sig_idx], target_p, sl_p

    def check_exit_signal(self, row, last_price, state, config):
        adaptive_steps = config.get("ADAPTIVE_TRAIL_STEPS", []) 
        adaptive_steps_arr = np.zeros((len(adaptive_steps), 2))
        for i, step in enumerate(adaptive_steps):
            adaptive_steps_arr[i, 0] = step['pnl_pct']
            adaptive_steps_arr[i, 1] = step.get('tighten_ratio', 1.0)
            
        return numba_check_exit(
            last_price, state['position'], state['entry_price'], state['max_price_seen'], state['min_price_seen'], state['sl_price'],
            row['atr'], config.get("TRAILING_ATR_MULT", 3.0), config.get("USE_ADAPTIVE_TRAIL", False), adaptive_steps_arr,
            be_guard_threshold=config.get("BE_GUARD_THRESHOLD", 0.0)
        )

    def run_streaming_backtest(self, df_1m, **kwargs):
        config = self.c.copy()
        mapping = {
            'use_sniper': 'USE_SNIPER', 'use_retest_maker': 'USE_RETEST_MAKER',
            'vol_mult': 'VOL_MULTIPLIER', 'atr_trail_mult': 'TRAILING_ATR_MULT',
            'risk_pct': 'RISK_PER_TRADE', 'ema_period': 'EMA_TREND_PERIOD',
            'adx_threshold': 'ADX_FILTER_LEVEL', 'donchian_period': 'DONCHIAN_PERIOD',
            'use_adaptive': 'USE_ADAPTIVE_TRAIL', 'adaptive_steps': 'ADAPTIVE_TRAIL_STEPS',
            'initial_sl_pct': 'INITIAL_SL_PCT', 'be_guard_threshold': 'BE_GUARD_THRESHOLD',
            'adx_4h_threshold': 'ADX_4H_THRESHOLD'
        }
        for k, v in kwargs.items(): config[mapping.get(k, k)] = v

        if 'pre_calculated_ind' in kwargs:
            df_1h_ind = kwargs['pre_calculated_ind']
        else:
            df_1h_base = get_all_base_bars(df_1m, config["SIGNAL_TIMEFRAME"], include_incomplete=True)
            df_4h_base = get_all_base_bars(df_1m, config["TREND_TIMEFRAME"], include_incomplete=True)
            df_1h_ind = self.calculate_indicators(df_1h_base, df_4h_base, config)

        if not isinstance(df_1h_ind.index, pd.DatetimeIndex):
            df_1h_ind.index = pd.to_datetime(df_1h_ind.index)
        
        m_times = df_1m['timestamp'].values.astype('datetime64[ns]')
        m_closes, m_highs, m_lows, m_vols = df_1m['close'].values, df_1m['high'].values, df_1m['low'].values, df_1m['volume'].values
        
        ind_data = df_1h_ind.to_dict('list')
        for k in ind_data: ind_data[k] = np.array(ind_data[k])
        
        idx_map = pd.Series(range(len(df_1h_ind)), index=df_1h_ind.index)
        valid_lookup_idx = idx_map.reindex(pd.DatetimeIndex(m_times), method='ffill').fillna(-1).astype(int).values

        i_upper, i_lower, i_atr, i_adx, i_avg_vol, i_ema_h = ind_data['upper'], ind_data['lower'], ind_data['atr'], ind_data['adx'], ind_data['avg_vol'], ind_data['ema_h']
        i_adx_4h = ind_data['adx_4h'] if 'adx_4h' in ind_data else np.zeros(len(i_upper))
        i_chop = ind_data['chop'] if 'chop' in ind_data else np.full(len(i_upper), 50.0)
        i_slope = ind_data['ema_slope'] if 'ema_slope' in ind_data else np.zeros(len(i_upper))
        i_chaos = ind_data['chaos'] if 'chaos' in ind_data else np.full(len(i_upper), 20.0)
        i_squeeze = ind_data['squeeze'] if 'squeeze' in ind_data else np.zeros(len(i_upper))

        steps = config.get("ADAPTIVE_TRAIL_STEPS", [])
        adaptive_steps_arr = np.zeros((len(steps), 2))
        for j, s in enumerate(steps):
            adaptive_steps_arr[j, 0], adaptive_steps_arr[j, 1] = s['pnl_pct'], s.get('tighten_ratio', 1.0)

        vol_mult, adx_threshold, initial_sl_atr, fixed_sl_pct, atr_trail_mult, prox_threshold, adx_4h_threshold, be_guard_threshold = \
            config.get("VOL_MULTIPLIER", 2.0), config.get("ADX_FILTER_LEVEL", 25.0), config.get("INITIAL_SL_ATR", 2.0), config.get("INITIAL_SL_PCT", 0.0), \
            config.get("TRAILING_ATR_MULT", 3.0), config.get("SNIPER_PROXIMITY_PCT", 0.005), config.get("ADX_4H_THRESHOLD", 20.0), config.get("BE_GUARD_THRESHOLD", 0.0)
        
        use_sniper, retest_maker, risk_pct, use_adaptive = \
            config.get("USE_SNIPER", True), config.get("USE_RETEST_MAKER", False), config.get("RISK_PER_TRADE", 0.02), config.get("USE_ADAPTIVE_TRAIL", False)

        i = 0
        while i < len(m_closes):
            idx = valid_lookup_idx[i]
            if idx == -1: i += 1; continue
            
            last_p, r_ema_h, r_upper, r_lower, r_atr, r_adx, r_adx_4h, r_avg_vol, r_chop, r_slope, r_chaos, r_squeeze = \
                m_closes[i], i_ema_h[idx], i_upper[idx], i_lower[idx], i_atr[idx], i_adx[idx], i_adx_4h[idx], i_avg_vol[idx], i_chop[idx], i_slope[idx], i_chaos[idx], i_squeeze[idx]

            if self.position != 0:
                exit_rel_idx, max_p, min_p = numba_find_first_exit(m_closes[i:], valid_lookup_idx[i:], self.position, self.entry_price, 
                    self.max_price_seen, self.min_price_seen, self.sl_price, i_atr, atr_trail_mult, use_adaptive, adaptive_steps_arr, be_guard_threshold)
                if exit_rel_idx != -1:
                    old_i = i; i += exit_rel_idx
                    for miss_i in range(old_i, i):
                        if miss_i % 1440 == 0: self.equity_curve.append(self.capital)
                    self.max_price_seen, self.min_price_seen = max_p, min_p
                    self._close_position(m_closes[i], pd.Timestamp(m_times[i]))
                    if i % 1440 == 0: self.equity_curve.append(self.capital)
                    i += 1; continue

            if self.position == 0 and pd.Timestamp(m_times[i]) > self.last_close_time:
                curr_bar_vol = np.sum(m_vols[i - (i % 60) : i+1])
                sig_type, target_p, sl_p = numba_check_entry(last_p, r_ema_h, r_upper, r_lower, r_atr, r_adx, r_avg_vol, curr_bar_vol,
                    vol_mult, adx_threshold, initial_sl_atr, use_sniper, retest_maker, prox_threshold, False, fixed_sl_pct, r_adx_4h, adx_4h_threshold, r_chop, r_slope, r_chaos, r_squeeze)
                
                if sig_type == 2 and ((target_p > r_ema_h and m_highs[i] >= target_p) or (target_p < r_ema_h and m_lows[i] <= target_p)):
                    self._open_position((1 if target_p > r_ema_h else -1), target_p, sl_p, pd.Timestamp(m_times[i]), risk_pct, True)
                elif sig_type == 1:
                    self._open_position((1 if target_p > r_ema_h else -1), target_p, sl_p, pd.Timestamp(m_times[i]), risk_pct)

            if i % 1440 == 0: self.equity_curve.append(self.capital)
            i += 1
        return self.trades, self.equity_curve, df_1h_ind

    def _open_position(self, side, price, sl, timestamp, risk_pct, is_sniper=False):
        self.position, self.entry_price, self.sl_price = side, price, sl
        self.max_price_seen, self.min_price_seen = price, price
        self.quantity = (self.capital * risk_pct) / abs(price - sl) if abs(price - sl) > 0 else 0
        self.trades.append({'time': timestamp, 'side': ('LONG' if side==1 else 'SHORT'), 'type': 'OPEN', 'price': price, 'is_sniper': is_sniper})

    def _close_position(self, price, timestamp):
        pnl = (price - self.entry_price) * self.quantity * self.position
        self.capital += pnl
        self.trades.append({'time': timestamp, 'side': ('LONG' if self.position==1 else 'SHORT'), 'type': 'CLOSE', 'price': price, 'pnl': pnl})
        self.position, self.entry_price, self.quantity, self.sl_price = 0, 0, 0, 0
        self.last_close_time = timestamp
