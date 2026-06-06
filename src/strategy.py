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
                      chop=50.0, ema_slope=0.0, chaos=20.0, chaos_threshold=20.0, squeeze=0.0):
    # --- V7.1 Momentum Chaos Engine (Restored Asymmetry) ---
    
    # 1. Parameter Normalization (Hysteresis)
    v_target = vol_mult * 0.8 if is_ambushing else vol_mult
    a_target = adx_threshold * 0.8 if is_ambushing else adx_threshold
    a4_target = adx_4h_threshold * 0.8 if is_ambushing else adx_4h_threshold
    p_target = prox_threshold * 2.0 if is_ambushing else prox_threshold

    # 2. Entry Candidate Classification
    is_long_cand = last_price > ema_h
    
    # 3. Dynamic Barrier (Bypassable if chaos_threshold is 0)
    v_mult_final = v_target
    a_target_final = a_target
    a4_target_final = a4_target
    
    if chaos_threshold > 0:
        # Chaos Spike Filter
        if chaos < chaos_threshold: return 0, 0.0, 0.0
        
        # Slope Filter
        if is_long_cand and ema_slope <= 0: return 0, 0.0, 0.0
        if not is_long_cand and ema_slope >= 0: return 0, 0.0, 0.0

        # Choppiness Scaling
        if chop > 61.8: v_mult_final *= 1.8
        elif chop < 38.2: v_mult_final *= 0.8
        if squeeze > 0: v_mult_final *= 0.7 
        
        # [RESTORED] Asymmetric Bias for Shorts: Fear is faster
        if not is_long_cand:
            v_mult_final *= 0.6  # Shorts trigger 40% easier on volume
            a_target_final *= 0.7 # Shorts trigger 30% easier on ADX
            a4_target_final *= 0.7

    # 4. Standard & MTF Filters
    if volume <= (avg_vol * v_mult_final) or adx <= a_target_final or adx_4h < a4_target_final:
        return 0, 0.0, 0.0

    if retest_maker:
        if is_long_cand and last_price > upper:
            sl = upper * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else upper - (atr * initial_sl_atr)
            return 3, upper, sl
        elif not is_long_cand and last_price < lower:
            sl = lower * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else lower + (atr * initial_sl_atr)
            return 3, lower, sl
    
    elif use_sniper:
        dist_top = (upper - last_price) / (last_price + 1e-10) if last_price < upper else -1.0
        dist_bottom = (last_price - lower) / (last_price + 1e-10) if last_price > lower else -1.0

        if is_long_cand and 0.0003 <= dist_top <= (p_target + 1e-6):
            sl = upper * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else upper - (atr * initial_sl_atr)
            return 2, upper, sl
        elif not is_long_cand and 0.0003 <= dist_bottom <= (p_target + 1e-6):
            sl = lower * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else lower + (atr * initial_sl_atr)
            return 2, lower, sl
        
        if is_long_cand and last_price >= (upper * 0.9997):
            sl = last_price * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else last_price - (atr * initial_sl_atr)
            return 1, last_price, sl
        elif not is_long_cand and last_price <= (lower * 1.0003):
            sl = last_price * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else last_price + (atr * initial_sl_atr)
            return 1, last_price, sl
    
    else:
        if is_long_cand and last_price > upper:
            sl = last_price * (1 - fixed_sl_pct) if fixed_sl_pct > 0 else last_price - (atr * initial_sl_atr)
            return 1, last_price, sl
        elif not is_long_cand and last_price < lower:
            sl = last_price * (1 + fixed_sl_pct) if fixed_sl_pct > 0 else last_price + (atr * initial_sl_atr)
            return 1, last_price, sl
            
    return 0, 0.0, 0.0

@njit
def numba_check_exit(last_price, position, entry_price, max_price_seen, min_price_seen, sl_price, 
                     atr, atr_trail_mult, use_adaptive, adaptive_steps_arr, be_guard_threshold=0.0):
    curr_atr_mult = atr_trail_mult
    pnl_pct = ((last_price / entry_price) - 1) * 100 * position

    if be_guard_threshold > 0 and pnl_pct >= be_guard_threshold:
        be_sl = entry_price * (1 + 0.001 * position)
        if position == 1: sl_price = max(sl_price, be_sl)
        else: sl_price = min(sl_price, be_sl) if sl_price > 0 else be_sl

    if use_adaptive:
        for i in range(len(adaptive_steps_arr)):
            if pnl_pct >= adaptive_steps_arr[i, 0]:
                curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[i, 1])

    if position == 1:
        trail_sl = max_price_seen - (atr * curr_atr_mult)
        return last_price <= trail_sl or last_price <= sl_price
    elif position == -1:
        trail_sl = min_price_seen + (atr * curr_atr_mult)
        return last_price >= trail_sl or (sl_price > 0 and last_price >= sl_price)
    return False

@njit
def numba_find_first_exit(closes, lookup_indices, position, entry_price, initial_max, initial_min, initial_sl,
                          atrs, atr_trail_mult, use_adaptive, adaptive_steps_arr, be_guard_threshold=0.0):
    max_p, min_p, sl_p = initial_max, initial_min, initial_sl
    for i in range(len(closes)):
        idx = lookup_indices[i]
        if idx == -1: continue 
        last_p = closes[i]
        atr = atrs[idx]
        pnl_pct = ((last_p / entry_price) - 1) * 100 * position

        if be_guard_threshold > 0 and pnl_pct >= be_guard_threshold:
            be_sl = entry_price * (1 + 0.001 * position)
            if position == 1: sl_p = max(sl_p, be_sl)
            else: sl_p = min(sl_p, be_sl) if sl_p > 0 else be_sl

        if position == 1:
            max_p = max(max_p, last_p)
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            trail_sl = max_p - (atr * curr_atr_mult)
            if last_p <= trail_sl or last_p <= sl_p: return i, max_p, min_p
        else:
            min_p = min(min_p, last_p)
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            trail_sl = min_p + (atr * curr_atr_mult)
            if last_p >= trail_sl or (sl_p > 0 and last_p >= sl_p): return i, max_p, min_p
    return -1, max_p, min_p

def get_all_base_bars(df_1m, timeframe, include_incomplete=False):
    df_1m = df_1m.copy()
    df_1m.set_index('timestamp', inplace=True)
    resampled = df_1m.resample(timeframe).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    })
    if not include_incomplete: resampled = resampled.dropna()
    return resampled.reset_index()

class TrendCrusherV2:
    def __init__(self, config=CONFIG):
        self.c = config
        self.capital = config.get("SEED", 10000)
        self.position, self.entry_price, self.quantity = 0, 0, 0
        self.max_price_seen, self.min_price_seen = 0, 0
        self.sl_price, self.entry_fee = 0, 0
        self.last_close_time = pd.Timestamp(0)
        self.trades, self.equity_curve = [], [self.capital]

    def calculate_indicators(self, df_sig, df_trend, config, is_live=False):
        df = df_sig.copy()
        has_ts = 'timestamp' in df.columns
        if not has_ts: df['timestamp'] = pd.date_range(start='2024-01-01', periods=len(df), freq='h')
        df['upper'], df['lower'] = calculate_donchian(df, period=config.get("DONCHIAN_PERIOD", 20))
        df['atr'], df['avg_vol'], df['adx'] = calculate_atr(df, 14), calculate_avg_vol(df, 20), calculate_adx(df, 14)
        df['chop'], df['chaos'], df['squeeze'] = calculate_choppiness(df, 14), calculate_chaos_index(df, 14), calculate_squeeze_score(df)
        df['ema_h'] = calculate_ema(df, config.get("EMA_TREND_PERIOD", 50) * 4)
        df['ema_slope'] = df['ema_h'].diff(3)
        df_4h = df_trend.copy()
        if 'timestamp' not in df_4h.columns: df_4h['timestamp'] = pd.date_range(start='2024-01-01', periods=len(df_4h), freq='4h')
        df_4h['adx_4h'] = calculate_adx(df_4h, 14)
        df = df.merge(df_4h[['timestamp', 'adx_4h']], on='timestamp', how='left').ffill().fillna(0.0)
        if has_ts: df = df.set_index('timestamp')
        return df

    def calculate_position_size(self, price, stop_loss_price, risk_pct):
        risk_amt = self.capital * risk_pct
        stop_dist = abs(price - stop_loss_price)
        return risk_amt / stop_dist if stop_dist > 0 else 0

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None, is_ambushing=False):
        c = config if config else self.c
        sig_idx, target_p, sl_p = numba_check_entry(
            last_price, row['ema_h'], row['upper'], row['lower'], row['atr'], row['adx'], row['avg_vol'], row['volume'],
            c.get("VOL_MULTIPLIER", 2.0), c.get("ADX_FILTER_LEVEL", 25.0), c.get("INITIAL_SL_ATR", 2.0),
            use_sniper, retest_maker, c.get("SNIPER_PROXIMITY_PCT", 0.005), is_ambushing,
            c.get("INITIAL_SL_PCT", 0.0), row.get('adx_4h', 0.0), c.get("ADX_4H_THRESHOLD", 20.0),
            row.get('chop', 50.0), row.get('ema_slope', 0.0), row.get('chaos', 20.0), c.get("CHAOS_THRESHOLD", 20.0), row.get('squeeze', 0.0)
        )
        sig_map = {0: None, 1: 'MARKET', 2: 'SNIPER', 3: 'RETEST'}
        return sig_map[sig_idx], target_p, sl_p

    def check_exit_signal(self, row, last_price, state, config):
        steps = config.get("ADAPTIVE_TRAIL_STEPS", []) 
        steps_arr = np.zeros((len(steps), 2))
        for i, s in enumerate(steps): steps_arr[i, 0], steps_arr[i, 1] = s['pnl_pct'], s.get('tighten_ratio', 1.0)
        return numba_check_exit(last_price, state['position'], state['entry_price'], state['max_price_seen'], state['min_price_seen'], state['sl_price'],
            row['atr'], config.get("TRAILING_ATR_MULT", 3.0), config.get("USE_ADAPTIVE_TRAIL", False), steps_arr, config.get("BE_GUARD_THRESHOLD", 0.0))

    def run_streaming_backtest(self, df_1m, **kwargs):
        config = self.c.copy()
        mapping = {'use_sniper': 'USE_SNIPER', 'use_retest_maker': 'USE_RETEST_MAKER', 'vol_mult': 'VOL_MULTIPLIER', 'atr_trail_mult': 'TRAILING_ATR_MULT',
            'risk_pct': 'RISK_PER_TRADE', 'ema_period': 'EMA_TREND_PERIOD', 'adx_threshold': 'ADX_FILTER_LEVEL', 'donchian_period': 'DONCHIAN_PERIOD',
            'use_adaptive': 'USE_ADAPTIVE_TRAIL', 'adaptive_steps': 'ADAPTIVE_TRAIL_STEPS', 'initial_sl_pct': 'INITIAL_SL_PCT', 
            'be_guard_threshold': 'BE_GUARD_THRESHOLD', 'adx_4h_threshold': 'ADX_4H_THRESHOLD', 'chaos_threshold': 'CHAOS_THRESHOLD'}
        for k, v in kwargs.items(): config[mapping.get(k, k)] = v
        df_1h_ind = kwargs.get('pre_calculated_ind')
        if df_1h_ind is None:
            df_1h_ind = self.calculate_indicators(get_all_base_bars(df_1m, config.get("SIGNAL_TIMEFRAME", "1h"), True), get_all_base_bars(df_1m, config.get("TREND_TIMEFRAME", "4h"), True), config)
        if not isinstance(df_1h_ind.index, pd.DatetimeIndex): df_1h_ind.index = pd.to_datetime(df_1h_ind.index)
        m_times, m_closes, m_highs, m_lows, m_vols = df_1m['timestamp'].values.astype('datetime64[ns]'), df_1m['close'].values, df_1m['high'].values, df_1m['low'].values, df_1m['volume'].values
        ind_data = df_1h_ind.to_dict('list')
        for k in ind_data: ind_data[k] = np.array(ind_data[k])
        valid_lookup_idx = pd.Series(range(len(df_1h_ind)), index=df_1h_ind.index).reindex(pd.DatetimeIndex(m_times), method='ffill').fillna(-1).astype(int).values
        i_upper, i_lower, i_atr, i_adx, i_avg_vol, i_ema_h = ind_data['upper'], ind_data['lower'], ind_data['atr'], ind_data['adx'], ind_data['avg_vol'], ind_data['ema_h']
        i_adx_4h, i_chop, i_slope, i_chaos, i_squeeze = ind_data.get('adx_4h', np.zeros(len(i_upper))), ind_data.get('chop', np.full(len(i_upper), 50.0)), ind_data.get('ema_slope', np.zeros(len(i_upper))), ind_data.get('chaos', np.full(len(i_upper), 20.0)), ind_data.get('squeeze', np.zeros(len(i_upper)))
        steps = config.get("ADAPTIVE_TRAIL_STEPS", [])
        steps_arr = np.zeros((len(steps), 2))
        for j, s in enumerate(steps): steps_arr[j, 0], steps_arr[j, 1] = s['pnl_pct'], s.get('tighten_ratio', 1.0)
        v_m, a_t, i_s_a, f_s_p, a_t_m, p_t, a_4_t, b_g_t, c_t = config["VOL_MULTIPLIER"], config["ADX_FILTER_LEVEL"], config["INITIAL_SL_ATR"], config["INITIAL_SL_PCT"], config["TRAILING_ATR_MULT"], config.get("SNIPER_PROXIMITY_PCT", 0.005), config["ADX_4H_THRESHOLD"], config["BE_GUARD_THRESHOLD"], config.get("CHAOS_THRESHOLD", 20.0)
        u_s, r_m, r_p, u_a = config.get("USE_SNIPER", True), config.get("USE_RETEST_MAKER", False), config.get("RISK_PER_TRADE", 0.02), config.get("USE_ADAPTIVE_TRAIL", False)
        i = 0
        while i < len(m_closes):
            idx = valid_lookup_idx[i]
            if idx == -1: i += 1; continue
            last_p, r_ema_h, r_upper, r_lower, r_atr, r_adx, r_adx_4h, r_avg_vol, r_chop, r_slope, r_chaos, r_squeeze = m_closes[i], i_ema_h[idx], i_upper[idx], i_lower[idx], i_atr[idx], i_adx[idx], i_adx_4h[idx], i_avg_vol[idx], i_chop[idx], i_slope[idx], i_chaos[idx], i_squeeze[idx]
            if self.position != 0:
                rel_idx, max_p, min_p = numba_find_first_exit(m_closes[i:], valid_lookup_idx[i:], self.position, self.entry_price, self.max_price_seen, self.min_price_seen, self.sl_price, i_atr, a_t_m, u_a, steps_arr, b_g_t)
                if rel_idx != -1:
                    old_i = i; i += rel_idx
                    for m_i in range(old_i, i):
                        if m_i % 1440 == 0: self.equity_curve.append(self.capital)
                    self.max_price_seen, self.min_price_seen = max_p, min_p
                    self._close_position(m_closes[i], pd.Timestamp(m_times[i]))
                    if i % 1440 == 0: self.equity_curve.append(self.capital)
                    i += 1; continue
            if self.position == 0 and pd.Timestamp(m_times[i]) > self.last_close_time:
                c_b_v = np.sum(m_vols[i - (i % 60) : i+1])
                sig_t, tar_p, sl_p = numba_check_entry(last_p, r_ema_h, r_upper, r_lower, r_atr, r_adx, r_avg_vol, c_b_v, v_m, a_t, i_s_a, u_s, r_m, p_t, False, f_s_p, r_adx_4h, a_4_t, r_chop, r_slope, r_chaos, c_t, r_squeeze)
                if sig_t == 2 and ((tar_p > r_ema_h and m_highs[i] >= tar_p) or (tar_p < r_ema_h and m_lows[i] <= tar_p)):
                    self._open_position((1 if tar_p > r_ema_h else -1), tar_p, sl_p, pd.Timestamp(m_times[i]), r_p, True)
                elif sig_t == 1: self._open_position((1 if tar_p > r_ema_h else -1), tar_p, sl_p, pd.Timestamp(m_times[i]), r_p)
            if i % 1440 == 0: self.equity_curve.append(self.capital)
            i += 1
        return self.trades, self.equity_curve, df_1h_ind

    def _open_position(self, side, price, sl, timestamp, risk_pct, is_sniper=False, is_maker=False):
        e_p = price
        if not is_maker:
            slip = e_p * 0.0005 
            e_p = e_p + slip if side == 1 else e_p - slip
        self.position, self.entry_price, self.sl_price = side, e_p, sl
        self.max_price_seen, self.min_price_seen = e_p, e_p
        self.quantity = self.calculate_position_size(e_p, sl, risk_pct)
        fee_r = 0.0002 if is_maker else 0.0005
        self.entry_fee = e_p * self.quantity * fee_r
        self.trades.append({'time': timestamp, 'side': ('LONG' if side==1 else 'SHORT'), 'type': 'OPEN', 'price': e_p, 'is_sniper': is_sniper, 'is_maker': is_maker})

    def _close_position(self, price, timestamp, is_maker=False):
        fee_r = 0.0002 if is_maker else 0.0005
        ex_f = price * self.quantity * fee_r
        pnl = (price - self.entry_price) * self.quantity * self.position
        net_pnl = pnl - (self.entry_fee + ex_f)
        self.capital += net_pnl
        self.trades.append({'time': timestamp, 'side': ('LONG' if self.position==1 else 'SHORT'), 'type': 'CLOSE', 'price': price, 'pnl': net_pnl, 'is_maker': is_maker, 'pnl_usdt': net_pnl})
        self.position, self.entry_price, self.quantity, self.sl_price, self.entry_fee = 0, 0, 0, 0, 0
        self.last_close_time = timestamp
