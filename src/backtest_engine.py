import numpy as np
import pandas as pd
from src.strategy_numba import numba_check_entry, numba_find_first_exit
from src.strategy import get_all_base_bars

class BacktestEngine:
    """
    Independent Backtesting Engine for BaseStrategy implementations.
    Executes a minute-by-minute (1m) streaming backtest simulation.
    """
    def __init__(self, strategy):
        self.strategy = strategy

    def run(self, df_1m, **kwargs):
        # Keep references to strategy state and config
        strategy = self.strategy
        config = strategy.c.copy()
        
        # Mapping parameter names from kwargs to CONFIG format
        mapping = {
            'use_sniper': 'USE_SNIPER', 
            'use_retest_maker': 'USE_RETEST_MAKER', 
            'vol_mult': 'VOL_MULTIPLIER', 
            'atr_trail_mult': 'TRAILING_ATR_MULT',
            'risk_pct': 'RISK_PER_TRADE', 
            'ema_period': 'EMA_TREND_PERIOD', 
            'adx_threshold': 'ADX_FILTER_LEVEL', 
            'donchian_period': 'DONCHIAN_PERIOD',
            'use_adaptive': 'USE_ADAPTIVE_TRAIL', 
            'adaptive_steps': 'ADAPTIVE_TRAIL_STEPS', 
            'initial_sl_pct': 'INITIAL_SL_PCT', 
            'be_guard_threshold': 'BE_GUARD_THRESHOLD', 
            'adx_4h_threshold': 'ADX_4H_THRESHOLD', 
            'chaos_threshold': 'CHAOS_THRESHOLD'
        }
        for k, v in kwargs.items(): 
            config[mapping.get(k, k)] = v
            
        df_1h_ind = kwargs.get('pre_calculated_ind')
        if df_1h_ind is None:
            df_1h_ind = strategy.calculate_indicators(
                get_all_base_bars(df_1m, config.get("SIGNAL_TIMEFRAME", "1h"), True), 
                get_all_base_bars(df_1m, config.get("TREND_TIMEFRAME", "4h"), True), 
                config
            )
            
        if not isinstance(df_1h_ind.index, pd.DatetimeIndex): 
            df_1h_ind.index = pd.to_datetime(df_1h_ind.index)
            
        m_times = df_1m['timestamp'].values.astype('datetime64[ns]')
        m_closes = df_1m['close'].values
        m_highs = df_1m['high'].values
        m_lows = df_1m['low'].values
        m_vols = df_1m['volume'].values
        
        ind_data = df_1h_ind.to_dict('list')
        for k in ind_data: 
            ind_data[k] = np.array(ind_data[k])
            
        valid_lookup_idx = pd.Series(range(len(df_1h_ind)), index=df_1h_ind.index).reindex(pd.DatetimeIndex(m_times), method='ffill').fillna(-1).astype(int).values
        i_upper = ind_data['upper']
        i_lower = ind_data['lower']
        i_atr = ind_data['atr']
        i_adx = ind_data['adx']
        i_avg_vol = ind_data['avg_vol']
        i_ema_h = ind_data['ema_h']
        
        i_adx_4h = ind_data.get('adx_4h', np.zeros(len(i_upper)))
        i_chop = ind_data.get('chop', np.full(len(i_upper), 50.0))
        i_slope = ind_data.get('ema_slope', np.zeros(len(i_upper)))
        i_chaos = ind_data.get('chaos', np.full(len(i_upper), 20.0))
        i_squeeze = ind_data.get('squeeze', np.zeros(len(i_upper)))
        
        steps = config.get("ADAPTIVE_TRAIL_STEPS", [])
        steps_arr = np.zeros((len(steps), 2))
        for j, s in enumerate(steps): 
            steps_arr[j, 0] = s['pnl_pct']
            steps_arr[j, 1] = s.get('tighten_ratio', 1.0)
            
        v_m = config.get("VOL_MULTIPLIER", 2.0)
        a_t = config.get("ADX_FILTER_LEVEL", 25.0)
        i_s_a = config.get("INITIAL_SL_ATR", 2.0)
        f_s_p = config.get("INITIAL_SL_PCT", 0.0)
        a_t_m = config.get("TRAILING_ATR_MULT", 3.0)
        p_t = config.get("SNIPER_PROXIMITY_PCT", 0.005)
        a_4_t = config.get("ADX_4H_THRESHOLD", 20.0)
        b_g_t = config.get("BE_GUARD_THRESHOLD", 0.0)
        c_t = config.get("CHAOS_THRESHOLD", 20.0)
        
        u_s = config.get("USE_SNIPER", True)
        r_m = config.get("USE_RETEST_MAKER", False)
        r_p = config.get("RISK_PER_TRADE", 0.02)
        u_a = config.get("USE_ADAPTIVE_TRAIL", False)
        
        i = 0
        while i < len(m_closes):
            idx = valid_lookup_idx[i]
            if idx == -1: 
                i += 1
                continue
                
            last_p = m_closes[i]
            r_ema_h = i_ema_h[idx]
            r_upper = i_upper[idx]
            r_lower = i_lower[idx]
            r_atr = i_atr[idx]
            r_adx = i_adx[idx]
            r_adx_4h = i_adx_4h[idx]
            r_avg_vol = i_avg_vol[idx]
            r_chop = i_chop[idx]
            r_slope = i_slope[idx]
            r_chaos = i_chaos[idx]
            r_squeeze = i_squeeze[idx]
            
            if strategy.position != 0:
                rel_idx, max_p, min_p = numba_find_first_exit(
                    m_closes[i:], valid_lookup_idx[i:], strategy.position, strategy.entry_price, 
                    strategy.max_price_seen, strategy.min_price_seen, strategy.sl_price, 
                    i_atr, a_t_m, u_a, steps_arr, b_g_t
                )
                if rel_idx != -1:
                    old_i = i
                    i += rel_idx
                    for m_i in range(old_i, i):
                        if m_i % 1440 == 0: 
                            strategy.equity_curve.append(strategy.capital)
                    strategy.max_price_seen = max_p
                    strategy.min_price_seen = min_p
                    strategy._close_position(m_closes[i], pd.Timestamp(m_times[i]))
                    if i % 1440 == 0: 
                        strategy.equity_curve.append(strategy.capital)
                    i += 1
                    continue
                    
            if strategy.position == 0 and pd.Timestamp(m_times[i]) > strategy.last_close_time:
                c_b_v = np.sum(m_vols[i - (i % 60) : i+1])
                sig_t, tar_p, sl_p = numba_check_entry(
                    last_p, r_ema_h, r_upper, r_lower, r_atr, r_adx, r_avg_vol, c_b_v, 
                    v_m, a_t, i_s_a, u_s, r_m, p_t, False, f_s_p, r_adx_4h, a_4_t, 
                    r_chop, r_slope, r_chaos, c_t, r_squeeze
                )
                if sig_t == 2 and ((tar_p > r_ema_h and m_highs[i] >= tar_p) or (tar_p < r_ema_h and m_lows[i] <= tar_p)):
                    strategy._open_position((1 if tar_p > r_ema_h else -1), tar_p, sl_p, pd.Timestamp(m_times[i]), r_p, True)
                elif sig_t == 1: 
                    strategy._open_position((1 if tar_p > r_ema_h else -1), tar_p, sl_p, pd.Timestamp(m_times[i]), r_p)
                    
            if i % 1440 == 0: 
                strategy.equity_curve.append(strategy.capital)
            i += 1
            
        return strategy.trades, strategy.equity_curve, df_1h_ind
