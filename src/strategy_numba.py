import numpy as np
from numba import njit

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

    # 1. Break-even Guard
    if be_guard_threshold > 0 and pnl_pct >= be_guard_threshold:
        be_sl = entry_price * (1 + 0.001 * position)
        if position == 1: sl_price = max(sl_price, be_sl)
        else: sl_price = min(sl_price, be_sl) if sl_price > 0 else be_sl

    # 2. Adaptive Trailing
    if use_adaptive:
        for i in range(len(adaptive_steps_arr)):
            if pnl_pct >= adaptive_steps_arr[i, 0]:
                curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[i, 1])

    # 3. Final SL Calculation & Trigger Check
    if position == 1:
        trail_sl = max_price_seen - (atr * curr_atr_mult)
        new_sl = max(sl_price, trail_sl)
        return last_price <= new_sl, new_sl
    else:
        trail_sl = min_price_seen + (atr * curr_atr_mult)
        new_sl = min(sl_price, trail_sl) if sl_price > 0 else trail_sl
        return last_price >= new_sl, new_sl

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
            max_p = max_p if max_p > last_p else last_p
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            trail_sl = max_p - (atr * curr_atr_mult)
            sl_p = max(sl_p, trail_sl)
            if last_p <= sl_p: return i, max_p, min_p
        else:
            min_p = min_p if min_p < last_p else last_p
            curr_atr_mult = atr_trail_mult
            if use_adaptive:
                for j in range(len(adaptive_steps_arr)):
                    if pnl_pct >= adaptive_steps_arr[j, 0]:
                        curr_atr_mult = min(curr_atr_mult, atr_trail_mult * adaptive_steps_arr[j, 1])
            trail_sl = min_p + (atr * curr_atr_mult)
            sl_p = min(sl_p, trail_sl) if sl_p > 0 else trail_sl
            if last_p >= sl_p: return i, max_p, min_p
    return -1, max_p, min_p
