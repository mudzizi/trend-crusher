import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx

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

    def calculate_indicators(self, df_sig, df_trend, config):
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

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None):
        c = config if config else self.c
        vol_mult = c.get("VOL_MULTIPLIER", 2.0)
        adx_threshold = c.get("ADX_FILTER_LEVEL", 25.0)
        initial_sl_atr = c.get("INITIAL_SL_ATR", 2.0)

        # Volume burst & ADX trend validation
        if row['volume'] <= (row['avg_vol'] * vol_mult) or row['adx'] <= adx_threshold:
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

            # Sniper: In proximity to breakout
            if last_price > row['ema_h'] and dist_top <= (prox_threshold + 1e-6):
                sl = row['upper'] - (row['atr'] * initial_sl_atr)
                return 'SNIPER', row['upper'], sl
            elif last_price < row['ema_h'] and dist_bottom <= (prox_threshold + 1e-6):
                sl = row['lower'] - (row['atr'] * initial_sl_atr) # Fixed: should be + for short? No, logic follows user's source
                return 'SNIPER', row['lower'], row['lower'] + (row['atr'] * initial_sl_atr)
            
            # Sniper Fallback: Already breakout
            if last_price > row['ema_h'] and last_price >= row['upper']:
                sl = last_price - (row['atr'] * initial_sl_atr)
                return 'SNIPER', last_price, sl
            elif last_price < row['ema_h'] and last_price <= row['lower']:
                sl = last_price + (row['atr'] * initial_sl_atr)
                return 'SNIPER', last_price, sl
        
        else:
            if last_price > row['ema_h'] and last_price > row['upper']:
                sl = last_price - (row['atr'] * initial_sl_atr)
                return 'MARKET', last_price, sl
            elif last_price < row['ema_h'] and last_price < row['lower']:
                sl = last_price + (row['atr'] * initial_sl_atr)
                return 'MARKET', last_price, sl
        
        return None, None, None

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
        config = self.c.copy()
        # KW mapping to match the realistic simulation script
        mapping = {'use_sniper': 'USE_SNIPER','use_retest_maker':'USE_RETEST_MAKER' , 'vol_mult': 'VOL_MULTIPLIER', 'atr_trail_mult': 'TRAILING_ATR_MULT', 'risk_pct': 'RISK_PER_TRADE', 'ema_period': 'EMA_TREND_PERIOD', 'adx_threshold': 'ADX_FILTER_LEVEL', 'donchian_period': 'DONCHIAN_PERIOD', 'use_adaptive': 'USE_ADAPTIVE_TRAIL', 'adaptive_steps': 'ADAPTIVE_TRAIL_STEPS'}
        for k, v in kwargs.items(): config[mapping.get(k, k)] = v
        
        # 부분 캔들 포함 모드로 1h, 4h 생성 (실시간 계산용)
        df_1h_base = get_all_base_bars(df_1m, config["SIGNAL_TIMEFRAME"], include_incomplete=True)
        df_4h_base = get_all_base_bars(df_1m, config["TREND_TIMEFRAME"], include_incomplete=True)
        df_1h_ind = self.calculate_indicators(df_1h_base, df_4h_base, config)
        
        m_times = pd.to_datetime(df_1m['timestamp']).values.astype('datetime64[s]')
        m_opens, m_highs, m_lows, m_closes, m_vols = df_1m['open'].values, df_1m['high'].values, df_1m['low'].values, df_1m['close'].values, df_1m['volume'].values
        
        pending_maker_order = None
        self.capital = config.get("SEED", 10000)
        self.trades, self.equity_curve, self.position = [], [self.capital], 0
        use_sniper, retest_maker, risk_pct = config.get("USE_SNIPER", True), config.get("USE_RETEST_MAKER", False), config.get("RISK_PER_TRADE", 0.02)
        
        print(f"🚀 [The 1201% Engine] Re-Initialized Simulation...")
        warmup = 200 * 60
        for i in range(warmup, len(df_1m)):
            curr_time = m_times[i]
            last_price = m_closes[i]
            current_bar_start = curr_time.astype('datetime64[h]')
            
            # ZERO-LAG REFERENCE: 10:15 uses the 09:00 bar (which closed at 10:00)
            prev_bar_idx = current_bar_start - np.timedelta64(1, 'h')
            
            try:
                row = df_1h_ind.loc[prev_bar_idx]
            except KeyError: continue

            if self.position != 0:
                # Update extremes before check to catch intra-minute movement
                if self.position == 1: self.max_price_seen = max(self.max_price_seen, last_price)
                else: self.min_price_seen = min(self.min_price_seen, last_price)
                
                state = {'position': self.position, 'entry_price': self.entry_price, 'max_price_seen': self.max_price_seen, 'min_price_seen': self.min_price_seen, 'sl_price': self.sl_price}
                if self.check_exit_signal(row, last_price, state, config):
                    self._close_position(last_price, pd.Timestamp(curr_time))
            
            elif pending_maker_order:
                if (pending_maker_order['side'] == 1 and m_lows[i] <= pending_maker_order['price']) or \
                   (pending_maker_order['side'] == -1 and m_highs[i] >= pending_maker_order['price']):
                    self._open_position(pending_maker_order['side'], pending_maker_order['price'], pending_maker_order['sl'], pd.Timestamp(curr_time), risk_pct, is_maker=True)
                    pending_maker_order = None
                elif (pd.Timestamp(curr_time) - pending_maker_order['timestamp']).total_seconds() > 14400:
                    pending_maker_order = None

            if self.position == 0 and not pending_maker_order and pd.Timestamp(curr_time) > self.last_close_time:
                # INTRA-BAR VOLUME SYNTHESIS
                current_bar_1m_start_idx = i - (i % 60)
                current_cum_vol = np.sum(m_vols[current_bar_1m_start_idx : i+1])
                
                live_row = row.copy()
                live_row['volume'] = current_cum_vol
                
                sig_type, target_p, sl_p = self.check_entry_signal(live_row, last_price, use_sniper, retest_maker, config)
                if sig_type == 'RETEST':
                    pending_maker_order = {'side': (1 if target_p > row['ema_h'] else -1), 'price': target_p, 'sl': sl_p, 'timestamp': pd.Timestamp(curr_time)}
                elif sig_type == 'SNIPER':
                    if (target_p > row['ema_h'] and m_highs[i] >= target_p) or (target_p < row['ema_h'] and m_lows[i] <= target_p):
                        self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_time), risk_pct, is_sniper=True)
                elif sig_type == 'MARKET':
                    self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_time), risk_pct)

            if i % 1440 == 0: self.equity_curve.append(self.capital)
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
