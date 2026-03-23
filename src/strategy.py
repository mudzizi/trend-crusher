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
        self.sl_order_id = None

    def calculate_indicators(self, df_1h, df_4h, config):
        df = df_1h.copy()
        df['upper'], df['lower'] = calculate_donchian(df, config.get('DONCHIAN_PERIOD', 20))
        df['ema_h'] = calculate_ema(df_4h, config.get('EMA_TREND_PERIOD', 200)).reindex(df['timestamp']).ffill().values
        df['atr'] = calculate_atr(df, config.get('ATR_PERIOD', 14))
        df['avg_vol'] = calculate_avg_vol(df, config.get('VOL_AVG_PERIOD', 20))
        df['adx'] = calculate_adx(df, config.get('ADX_PERIOD', 14))
        return df.dropna()

    def _open_position(self, direction, price, sl, timestamp, risk_pct, is_sniper=False, is_maker=False):
        if self.position != 0: return
        
        effective_slippage = 0
        if not is_maker:
            effective_slippage = (0.0001 if is_sniper else 0.0005)
        
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
        actual_pnl_usdt = pnl - fee
        self.capital += actual_pnl_usdt
        self.trades.append({'time': timestamp, 'type': 'CLOSE', 'price': price, 'pnl_usdt': actual_pnl_usdt})
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
        
        # Hysteresis
        if is_ambushing:
            vol_m *= 0.8
            adx_f *= 0.8
            prox_p *= 2.0

        if row['volume'] < row['avg_vol'] * vol_m: return None, 0, 0
        if row['adx'] < adx_f: return None, 0, 0

        # Long
        if last_price > row['ema_h']:
            target = row['upper']
            if last_price >= target: return 'MARKET', last_price, last_price - (row['atr'] * sl_atr)
            if use_sniper and last_price >= target * (1 - prox_p): return 'SNIPER', target, target - (row['atr'] * sl_atr)
            if retest_maker: return 'RETEST', target, target - (row['atr'] * sl_atr)
        
        # Short
        elif last_price < row['ema_h']:
            target = row['lower']
            if last_price <= target: return 'MARKET', last_price, last_price + (row['atr'] * sl_atr)
            if use_sniper and last_price <= target * (1 + prox_p): return 'SNIPER', target, target + (row['atr'] * sl_atr)
            if retest_maker: return 'RETEST', target, target + (row['atr'] * sl_atr)
            
        return None, 0, 0

    def check_exit_signal(self, row, last_price, state, config):
        if state['position'] == 1:
            if last_price <= state['sl_price']: return True
            # Trailing
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
        
        # 1. Indicator Setup
        df_ind = kwargs.get('pre_calculated_ind')
        if df_ind is None:
            df_1h = get_all_base_bars(df_1m, "1h")
            df_4h = get_all_base_bars(df_1m, "4h")
            df_ind = self.calculate_indicators(df_1h, df_4h, config)
        
        # 2. Vectorization (Convert to NumPy for speed)
        m_times = df_1m['timestamp'].values
        m_closes = df_1m['close'].values
        m_highs = df_1m['high'].values
        m_lows = df_1m['low'].values
        m_vols = df_1m['volume'].values
        
        ind_shifted = df_ind.shift(1)
        ind_times = ind_shifted['timestamp'].values.astype('datetime64[m]')
        
        # Create a dict of arrays for the loop
        cols = ['upper', 'lower', 'ema_h', 'atr', 'avg_vol', 'adx']
        ind_arrs = {c: ind_shifted[c].values for c in cols}
        
        self.capital = config.get("SEED", 10000)
        self.trades = []
        self.equity_curve = [self.capital]
        self.position = 0
        pending_maker = None
        
        use_sniper = config.get("USE_SNIPER", True)
        retest_maker = config.get("USE_RETEST_MAKER", False)
        risk_pct = config.get("RISK_PER_TRADE", 0.02)

        # 3. Optimized Loop
        for i in range(200 * 60, len(df_1m)):
            curr_t = m_times[i]
            # Use floor to find the hour bar
            hour_ts = curr_t.astype('datetime64[h]')
            
            # Find index in ind_times
            # Since both are sorted, we can use an index tracker but searchsorted is fast enough for now
            idx = np.searchsorted(ind_times, curr_t, side='right') - 1
            if idx < 0 or np.isnan(ind_arrs['upper'][idx]): continue
            
            # Fast row access
            row = {c: ind_arrs[c][idx] for c in cols}
            last_p = m_closes[i]
            
            if self.position != 0:
                state = {'position': self.position, 'sl_price': self.sl_price}
                if self.check_exit_signal(row, last_p, state, config):
                    self._close_position(last_p, pd.Timestamp(curr_t))
            elif pending_maker:
                # Maker logic
                sig_type_h, _, _ = self.check_entry_signal(row, last_p, use_sniper, retest_maker, config, is_ambushing=True)
                if sig_type_h != 'RETEST': pending_maker = None
                elif (pending_maker['side'] == 1 and m_lows[i] <= pending_maker['price']) or \
                     (pending_maker['side'] == -1 and m_highs[i] >= pending_maker['price']):
                    self._open_position(pending_maker['side'], pending_maker['price'], pending_maker['sl'], pd.Timestamp(curr_t), risk_pct, is_maker=True)
                    pending_maker = None
            else:
                # Entry discovery
                vol_start_idx = i - (i % 60)
                current_cum_vol = np.sum(m_vols[vol_start_idx : i+1])
                
                live_row = row.copy()
                live_row['volume'] = current_cum_vol
                
                sig_type, target_p, sl_p = self.check_entry_signal(live_row, last_p, use_sniper, retest_maker, config)
                
                if sig_type == 'RETEST':
                    pending_maker = {'side': (1 if target_p > row['ema_h'] else -1), 'price': target_p, 'sl': sl_p}
                elif sig_type == 'SNIPER':
                    if (target_p > row['ema_h'] and m_highs[i] >= target_p) or (target_p < row['ema_h'] and m_lows[i] <= target_p):
                        self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_t), risk_pct, is_sniper=True)
                elif sig_type == 'MARKET':
                    self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_t), risk_pct)

            if i % 1440 == 0: self.equity_curve.append(self.capital)
                
        return self.trades, self.equity_curve, df_ind
