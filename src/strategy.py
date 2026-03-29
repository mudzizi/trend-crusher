import pandas as pd
import numpy as np
from numba import njit
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx

@njit
def numba_check_entry(last_price, ema_h, upper, lower, atr, adx, avg_vol, volume, 
                      vol_mult, adx_threshold, initial_sl_atr, 
                      use_sniper, retest_maker, prox_threshold, is_ambushing=False):
    # Hysteresis: Loosen filters by 20% if already ambushing to prevent order flickering
    v_mult = vol_mult * 0.8 if is_ambushing else vol_mult
    a_thresh = adx_threshold * 0.8 if is_ambushing else adx_threshold
    p_thresh = prox_threshold * 2.0 if is_ambushing else prox_threshold

    # Volume burst & ADX trend validation
    if volume <= (avg_vol * v_mult) or adx <= a_thresh:
        return 0, 0.0, 0.0 # 0=None, 1=MARKET, 2=SNIPER, 3=RETEST

    if retest_maker:
        if last_price > ema_h and last_price > upper:
            sl = upper - (atr * initial_sl_atr)
            return 3, upper, sl
        elif last_price < ema_h and last_price < lower:
            sl = lower + (atr * initial_sl_atr)
            return 3, lower, sl
    
    elif use_sniper:
        dist_top = abs(last_price - upper) / (last_price + 1e-10)
        dist_bottom = abs(last_price - lower) / (last_price + 1e-10)

        # Sniper: In proximity to breakout
        if last_price > ema_h and dist_top <= (p_thresh + 1e-6):
            sl = upper - (atr * initial_sl_atr)
            return 2, upper, sl
        elif last_price < ema_h and dist_bottom <= (p_thresh + 1e-6):
            sl = lower + (atr * initial_sl_atr)
            return 2, lower, lower + (atr * initial_sl_atr)
        
        # Sniper Fallback: Already breakout
        if last_price > ema_h and last_price >= upper:
            sl = last_price - (atr * initial_sl_atr)
            return 2, last_price, sl
        elif last_price < ema_h and last_price <= lower:
            sl = last_price + (atr * initial_sl_atr)
            return 2, last_price, sl
    
    else:
        if last_price > ema_h and last_price > upper:
            sl = last_price - (atr * initial_sl_atr)
            return 1, last_price, sl
        elif last_price < ema_h and last_price < lower:
            sl = last_price + (atr * initial_sl_atr)
            return 1, last_price, sl
            
    return 0, 0.0, 0.0

@njit
def numba_check_exit(last_price, position, entry_price, max_price_seen, min_price_seen, sl_price, 
                     atr, atr_trail_mult, use_adaptive, adaptive_steps_arr):
    curr_atr_mult = atr_trail_mult
    pnl_pct = ((last_price / entry_price) - 1) * 100 * position

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
        if last_price >= trail_sl or last_price >= sl_price: return True
    return False

@njit
def numba_find_first_exit(closes, lookup_indices, position, entry_price, initial_max, initial_min, initial_sl,
                          atrs, atr_trail_mult, use_adaptive, adaptive_steps_arr):
    max_p = initial_max
    min_p = initial_min
    
    for i in range(len(closes)):
        idx = lookup_indices[i]
        if idx == -1: continue # Skip if no indicators
        
        last_p = closes[i]
        atr = atrs[idx]
        
        if position == 1:
            max_p = max(max_p, last_p)
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                pnl_pct = ((last_p / entry_price) - 1) * 100
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            
            trail_sl = max_p - (atr * curr_atr_mult)
            if last_p <= trail_sl or last_p <= initial_sl:
                return i, max_p, min_p
        else:
            min_p = min(min_p, last_p)
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                pnl_pct = ((last_p / entry_price) - 1) * 100 * -1
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            
            trail_sl = min_p + (atr * curr_atr_mult)
            if last_p >= trail_sl or last_p >= initial_sl:
                return i, max_p, min_p
                
    return -1, max_p, min_p

def get_all_base_bars(df_1m, timeframe, include_incomplete=False):
    """
    Resample 1m OHLCV to higher timeframe.
    
    Args:
        df_1m: DataFrame with 1m data (columns: timestamp, open, high, low, close, volume)
        timeframe: Target timeframe (e.g., '1h', '4h')
        include_incomplete: If True, include current incomplete candle. If False, only completed candles.
    
    Returns:
        DataFrame with resampled OHLCV data
    """
    df_1m = df_1m.copy()
    df_1m.set_index('timestamp', inplace=True)
    resampled = df_1m.resample(timeframe).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    })
    
    if not include_incomplete:
        # 기존 동작: 완성된 캔들만
        resampled = resampled.dropna()
    else:
        # 완성된 캔들들 + 현재 진행 중인 부분 캔들
        completed = resampled.dropna()
        if len(resampled) > len(completed):
            # 마지막 불완전한 캔들 추가
            resampled = pd.concat([completed, resampled.iloc[-1:]])
        else:
            resampled = completed
    
    return resampled.reset_index()

class TrendCrusherV2:
    def __init__(self, config):
        self.c = config
        self.initial_capital = config.get("SEED", 10000)
        self.capital = self.initial_capital
        self.position = 0 
        self.entry_price = 0
        self.quantity = 0
        self.sl_price = 0
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.last_close_time = pd.Timestamp.min
        self.trades = []
        self.equity_curve = []

    def calculate_indicators(self, df_sig, df_trend, config, is_live=False):
        df = df_sig.copy()
        if 'timestamp' not in df.columns: df = df.reset_index()
            
        df['upper'], df['lower'] = calculate_donchian(df, period=config.get("DONCHIAN_PERIOD", 20))
        df['atr'] = calculate_atr(df, period=config.get("ATR_PERIOD", 14))
        df['avg_vol'] = calculate_avg_vol(df, period=config.get("AVG_VOL_PERIOD", 20))
        df['adx'] = calculate_adx(df, period=config.get("ADX_PERIOD", 14))
        
        df_t = df_trend.copy()
        if 'timestamp' not in df_t.columns: df_t = df_t.reset_index()
            
        ema_vals = calculate_ema(df_t, period=config.get("EMA_TREND_PERIOD", 200))
        df_h = pd.DataFrame({'timestamp': df_t['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df = df.set_index('timestamp').join(df_h).ffill()
        return df

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None, is_ambushing=False):
        c = config if config else self.c
        vol_mult = c.get("VOL_MULTIPLIER", 2.0)
        adx_threshold = c.get("ADX_FILTER_LEVEL", 25.0)
        initial_sl_atr = c.get("INITIAL_SL_ATR", 2.0)
        prox_threshold = c.get("SNIPER_PROXIMITY_PCT", 0.005)

        # Use the Numba version for consistency and speed, even in single checks
        sig_idx, target_p, sl_p = numba_check_entry(
            last_price, row['ema_h'], row['upper'], row['lower'], row['atr'], row['adx'], row['avg_vol'], row['volume'],
            vol_mult, adx_threshold, initial_sl_atr, use_sniper, retest_maker, prox_threshold, is_ambushing
        )
        
        sig_map = {0: None, 1: 'MARKET', 2: 'SNIPER', 3: 'RETEST'}
        return sig_map[sig_idx], target_p, sl_p

    def check_exit_signal(self, row, last_price, state, config):
        atr_trail_mult = config.get("TRAILING_ATR_MULT", 3.0)
        use_adaptive = config.get("USE_ADAPTIVE_TRAIL", False)
        adaptive_steps = config.get("ADAPTIVE_TRAIL_STEPS", [])

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
            if last_price <= trail_sl or last_price <= state['sl_price']: return True
        elif state['position'] == -1:
            trail_sl = state['min_price_seen'] + (row['atr'] * curr_atr_mult)
            if last_price >= trail_sl or last_price >= state['sl_price']: return True
        return False

    def run_streaming_backtest(self, df_1m, **kwargs):
        sentinel = kwargs.get('sentinel', None)
        config = self.c.copy()
        # ... (기존 mapping 로직 생략되지 않도록 주의)
        mapping = {
            'use_sniper': 'USE_SNIPER', 'use_retest_maker': 'USE_RETEST_MAKER',
            'vol_mult': 'VOL_MULTIPLIER', 'atr_trail_mult': 'TRAILING_ATR_MULT',
            'risk_pct': 'RISK_PER_TRADE', 'ema_period': 'EMA_TREND_PERIOD',
            'adx_threshold': 'ADX_FILTER_LEVEL', 'donchian_period': 'DONCHIAN_PERIOD',
            'use_adaptive': 'USE_ADAPTIVE_TRAIL', 'adaptive_steps': 'ADAPTIVE_TRAIL_STEPS'
        }
        for k, v in kwargs.items(): config[mapping.get(k, k)] = v
        
        if 'pre_calculated_ind' in kwargs:
            df_1h_ind = kwargs['pre_calculated_ind']
        else:
            df_1h_base = get_all_base_bars(df_1m, config["SIGNAL_TIMEFRAME"], include_incomplete=True)
            df_4h_base = get_all_base_bars(df_1m, config["TREND_TIMEFRAME"], include_incomplete=True)
            df_1h_ind = self.calculate_indicators(df_1h_base, df_4h_base, config)
        
        # --- NumPy Optimization: Extract arrays before loop ---
        m_times = pd.to_datetime(df_1m['timestamp']).values.astype('datetime64[s]')
        m_opens = df_1m['open'].values
        m_highs = df_1m['high'].values
        m_lows = df_1m['low'].values
        m_closes = df_1m['close'].values
        m_vols = df_1m['volume'].values

        # Index mapping for indicators (1h to 1m alignment)
        # Create a lookup array for indicator indices
        if 'timestamp' in df_1h_ind.columns:
            ind_timestamps = df_1h_ind['timestamp'].values.astype('datetime64[s]')
        else:
            ind_timestamps = df_1h_ind.index.values.astype('datetime64[s]')
        
        ind_data = {col: df_1h_ind[col].values for col in df_1h_ind.columns}
        
        # Pre-map 1m timestamps to indicator indices to avoid hash lookups in loop
        # We need row[prev_bar_idx] where prev_bar_idx is current_hour - 1h
        m_hour_ts = m_times.astype('datetime64[h]')
        prev_hour_ts = (m_hour_ts - np.timedelta64(1, 'h')).astype('datetime64[s]')
        
        # Use searchsorted for fast index mapping
        # We want the MOST RECENT indicator bar that is <= prev_hour_ts
        lookup_idx = np.searchsorted(ind_timestamps, prev_hour_ts, side='right') - 1
        
        # Validate indices
        valid_lookup_idx = np.where(lookup_idx >= 0, lookup_idx, -1)

        # Pre-convert adaptive steps for Numba
        use_adaptive = config.get("USE_ADAPTIVE_TRAIL", False)
        adaptive_steps = config.get("ADAPTIVE_TRAIL_STEPS", [])
        adaptive_steps_arr = np.zeros((len(adaptive_steps), 2))
        for i, step in enumerate(adaptive_steps):
            adaptive_steps_arr[i, 0] = step['pnl_pct']
            adaptive_steps_arr[i, 1] = step.get('tighten_ratio', 1.0)
        
        pending_maker_order = None
        self.capital = config.get("SEED", 10000)
        self.trades, self.equity_curve, self.position = [], [self.capital], 0
        use_sniper = config.get("USE_SNIPER", True)
        retest_maker = config.get("USE_RETEST_MAKER", False)
        risk_pct = config.get("RISK_PER_TRADE", 0.02)
        
        # Scalar config values
        vol_mult = config.get("VOL_MULTIPLIER", 2.0)
        adx_threshold = config.get("ADX_FILTER_LEVEL", 25.0)
        initial_sl_atr = config.get("INITIAL_SL_ATR", 2.0)
        atr_trail_mult = config.get("TRAILING_ATR_MULT", 3.0)
        prox_threshold = config.get("SNIPER_PROXIMITY_PCT", 0.005)

        print(f"🚀 [Jump Engine] Starting Numba-Vectorized Simulation...")
        # If indicators are pre-calculated, we don't need warmup within the loop
        warmup = 0 if 'pre_calculated_ind' in kwargs else (120 * 60)
        
        # Cache indicator columns as separate arrays for faster access
        i_upper = ind_data['upper']
        i_lower = ind_data['lower']
        i_atr = ind_data['atr']
        i_adx = ind_data['adx']
        i_avg_vol = ind_data['avg_vol']
        i_ema_h = ind_data['ema_h']
        i_chop = ind_data['chop'] if 'chop' in ind_data else np.full(len(i_upper), 50.0)

        i = warmup
        while i < len(df_1m):
            if self.position != 0:
                # ---------------- JUMP TO EXIT ----------------
                exit_rel_idx, max_p, min_p = numba_find_first_exit(
                    m_closes[i:], valid_lookup_idx[i:], self.position, self.entry_price, 
                    self.max_price_seen, self.min_price_seen, self.sl_price,
                    i_atr, atr_trail_mult, use_adaptive, adaptive_steps_arr
                )
                
                old_i = i
                if exit_rel_idx != -1:
                    i = old_i + exit_rel_idx
                    # Capture capital BEFORE closing for equity curve backfilling
                    cap_before = self.capital
                    
                    # Fill equity curve for any daily marks missed BEFORE the exit minute
                    for miss_i in range(old_i, i):
                        if miss_i % 1440 == 0: self.equity_curve.append(cap_before)
                    
                    self.max_price_seen = max_p
                    self.min_price_seen = min_p
                    self._close_position(m_closes[i], pd.Timestamp(m_times[i]))
                    
                    # If the exit minute itself is a daily mark, use the AFTER-close capital
                    if i % 1440 == 0: self.equity_curve.append(self.capital)
                    
                    i += 1
                    continue
                else:
                    # No exit until end of data - Fill all remaining marks with current capital
                    for miss_i in range(old_i, len(df_1m)):
                        if miss_i % 1440 == 0: self.equity_curve.append(self.capital)
                    self.max_price_seen = max_p
                    self.min_price_seen = min_p
                    break # End simulation


            idx = valid_lookup_idx[i]
            if idx == -1: 
                i += 1
                continue
            
            last_p = m_closes[i]
            
            # Row data equivalent
            r_upper = i_upper[idx]
            r_lower = i_lower[idx]
            r_atr = i_atr[idx]
            r_adx = i_adx[idx]
            r_avg_vol = i_avg_vol[idx]
            r_ema_h = i_ema_h[idx]

            if pending_maker_order:
                if (pending_maker_order['side'] == 1 and m_lows[i] <= pending_maker_order['price']) or \
                   (pending_maker_order['side'] == -1 and m_highs[i] >= pending_maker_order['price']):
                    self._open_position(pending_maker_order['side'], pending_maker_order['price'], pending_maker_order['sl'], pd.Timestamp(m_times[i]), risk_pct, is_maker=True)
                    pending_maker_order = None
                elif (m_times[i] - pending_maker_order['ts_raw']).astype(int) > 14400:
                    pending_maker_order = None

            if self.position == 0 and not pending_maker_order and pd.Timestamp(m_times[i]) > self.last_close_time:
                # Intra-bar volume
                current_bar_1m_start_idx = i - (i % 60)
                current_cum_vol = np.sum(m_vols[current_bar_1m_start_idx : i+1])
                
                # Numba Entry Check
                sig_type, target_p, sl_p = numba_check_entry(last_p, r_ema_h, r_upper, r_lower, r_atr, r_adx, r_avg_vol, current_cum_vol,
                                                            vol_mult, adx_threshold, initial_sl_atr, 
                                                            use_sniper, retest_maker, prox_threshold)
                
                # --- Sentinel Check (If exists) ---
                if sentinel and sig_type > 0:
                    # Create a temporary row-like dict for sentinel
                    row_data = {'chop': i_chop[idx] if 'chop' in ind_data else 50.0}
                    is_safe, reason = sentinel.is_market_safe(row_data)
                    if not is_safe:
                        sig_type = 0 # Reject entry
                # ----------------------------------
                
                if sig_type == 3: # RETEST
                    pending_maker_order = {'side': (1 if target_p > r_ema_h else -1), 'price': target_p, 'sl': sl_p, 'timestamp': pd.Timestamp(m_times[i]), 'ts_raw': m_times[i]}
                elif sig_type == 2: # SNIPER
                    if (target_p > r_ema_h and m_highs[i] >= target_p) or (target_p < r_ema_h and m_lows[i] <= target_p):
                        self._open_position((1 if target_p > r_ema_h else -1), target_p, sl_p, pd.Timestamp(m_times[i]), risk_pct, is_sniper=True)
                elif sig_type == 1: # MARKET
                    self._open_position((1 if target_p > r_ema_h else -1), target_p, sl_p, pd.Timestamp(m_times[i]), risk_pct)

            if i % 1440 == 0: self.equity_curve.append(self.capital)
            i += 1
            
        return self.trades, self.equity_curve, df_1h_ind

    def _open_position(self, direction, price, sl_price, timestamp, risk_pct, is_sniper=False, is_maker=False):
        effective_slippage = 0 if is_maker else (0.0001 if is_sniper else 0.0005)
        self.entry_price = price * (1 + (effective_slippage * direction))
        self.sl_price = sl_price
        self.quantity = self.calculate_position_size(self.entry_price, self.sl_price, risk_pct)
        if self.quantity > 0:
            fee = self.entry_price * self.quantity * (0.0002 if is_maker else 0.0005)
            self.capital -= fee
            self.position, self.max_price_seen, self.min_price_seen = direction, self.entry_price, self.entry_price
            self.trades.append({'time': timestamp, 'type': 'OPEN', 'side': 'LONG' if direction==1 else 'SHORT', 'price': self.entry_price, 'qty': self.quantity, 'is_sniper': is_sniper, 'is_maker': is_maker})

    def _close_position(self, price, timestamp):
        pnl = (price - self.entry_price) * self.quantity * self.position
        fee = price * self.quantity * 0.0005
        self.capital += (pnl - fee)
        self.trades.append({'time': timestamp, 'type': 'CLOSE', 'price': price, 'pnl_usdt': pnl - fee})
        self.position = 0
        self.last_close_time = timestamp

    def calculate_position_size(self, price, stop_loss_price, risk_pct):
        risk_amt = self.capital * risk_pct
        stop_dist = abs(price - stop_loss_price)
        return risk_amt / stop_dist if stop_dist > 0 else 0
