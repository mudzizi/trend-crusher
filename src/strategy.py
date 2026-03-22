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
        if 'timestamp' not in df.columns:
            df = df.reset_index()
            
        df['upper'], df['lower'] = calculate_donchian(df, period=config.get("DONCHIAN_PERIOD", 20))
        df['atr'] = calculate_atr(df, period=config.get("ATR_PERIOD", 14))
        df['avg_vol'] = calculate_avg_vol(df, period=config.get("AVG_VOL_PERIOD", 20))
        df['adx'] = calculate_adx(df, period=config.get("ADX_PERIOD", 14))
        
        # Trend data processing
        df_t = df_trend.copy()
        if 'timestamp' not in df_t.columns:
            df_t = df_t.reset_index()
            
        ema_vals = calculate_ema(df_t, period=config.get("EMA_TREND_PERIOD", 200))
        df_h = pd.DataFrame({'timestamp': df_t['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df = df.set_index('timestamp').join(df_h).ffill()
        
        # Add persistence features to prevent signal loss during candle transitions
        df['prev_volume'] = df['volume'].shift(1)
        df['prev_avg_vol'] = df['avg_vol'].shift(1)
        
        return df

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None, is_ambushing=False):
        """
        Logic to determine if a new position should be opened.
        Returns: (signal_type, price, sl_price) or (None, None, None)
        """
        c = config if config else self.c
        vol_mult = c.get("VOL_MULTIPLIER", 2.0)
        adx_threshold = c.get("ADX_FILTER_LEVEL", 25.0)
        initial_sl_atr = c.get("INITIAL_SL_ATR", 2.0)

        # Apply Hysteresis: If already ambushing, allow signal to be slightly weaker (80% of threshold)
        hysteresis_mult = 0.8 if is_ambushing else 1.0
        
        # Volume Burst Persistence: Check current OR previous bar
        curr_burst = row['volume'] > (row['avg_vol'] * vol_mult * hysteresis_mult)
        prev_burst = row.get('prev_volume', 0) > (row.get('prev_avg_vol', 0) * vol_mult * hysteresis_mult)
        is_vol_burst = curr_burst or prev_burst
        
        is_trending = row['adx'] > (adx_threshold * hysteresis_mult)
        
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
            # Apply wider proximity hysteresis if already ambushing (1.0% vs 0.5%)
            prox_mult = 2.0 if is_ambushing else 1.0
            
            dist_top = abs(last_price - row['upper']) / (last_price + 1e-10)
            dist_bottom = abs(last_price - row['lower']) / (last_price + 1e-10)

            # Sniper Ambush: Close to breakout level (with small epsilon for precision)
            if last_price > row['ema_h'] and dist_top <= (prox_threshold * prox_mult + 1e-6):
                sl = row['upper'] - (row['atr'] * initial_sl_atr)
                return 'SNIPER', row['upper'], sl
            elif last_price < row['ema_h'] and dist_bottom <= (prox_threshold * prox_mult + 1e-6):
                sl = row['lower'] + (row['atr'] * initial_sl_atr)
                return 'SNIPER', row['lower'], sl
            
            # Sniper Fallback: Price already breakout
            if last_price > row['ema_h'] and last_price >= row['upper']:
                sl = last_price - (row['atr'] * initial_sl_atr)
                return 'SNIPER', last_price, sl
            elif last_price < row['ema_h'] and last_price <= row['lower']:
                sl = last_price + (row['atr'] * initial_sl_atr)
                return 'SNIPER', last_price, sl
        
        else:
            # Market (Close-based)
            if last_price > row['ema_h'] and last_price > row['upper']:
                sl = last_price - (row['atr'] * initial_sl_atr)
                return 'MARKET', last_price, sl
            elif last_price < row['ema_h'] and last_price < row['lower']:
                sl = last_price + (row['atr'] * initial_sl_atr)
                return 'MARKET', last_price, sl
        
        return None, None, None

    def run_precision_backtest(self, df_sig, df_trend, df_check, **kwargs):
        """
        Fast precision backtest runner. Required for OptimizerEngine.
        Uses pre-calculated indicator dataframes.
        """
        config = self.c.copy()
        mapping = {'vol_mult': 'VOL_MULTIPLIER', 'atr_trail_mult': 'TRAILING_ATR_MULT', 'risk_pct': 'RISK_PER_TRADE', 'ema_period': 'EMA_TREND_PERIOD', 'adx_threshold': 'ADX_FILTER_LEVEL', 'donchian_period': 'DONCHIAN_PERIOD'}
        for kw, cfg_key in mapping.items():
            if kw in kwargs: config[cfg_key] = kwargs[kw]

        df = self.calculate_indicators(df_sig, df_trend, config)
        df_check_idx = df_check.set_index(pd.to_datetime(df_check['timestamp']))
        
        pending_maker_order = None
        use_sniper = kwargs.get('use_sniper', config.get("USE_SNIPER", False))
        retest_maker = kwargs.get('retest_maker', config.get("USE_RETEST_MAKER", False))
        risk_pct = config.get("RISK_PER_TRADE", 0.02)

        for i in range(max(config.get("DONCHIAN_PERIOD", 20), 1), len(df)):
            row = df.iloc[i]
            curr_time = pd.to_datetime(row['timestamp'])
            if curr_time not in df_check_idx.index: continue
            
            if self.position != 0:
                tf_delta = pd.to_timedelta(config["SIGNAL_TIMEFRAME"])
                intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                for m_time, m_row in intra_data.iterrows():
                    state = {'position': self.position, 'entry_price': self.entry_price, 'max_price_seen': self.max_price_seen, 'min_price_seen': self.min_price_seen, 'sl_price': self.sl_price}
                    if self.check_exit_signal(row, m_row['close'], state, config):
                        self._close_position(m_row['close'], m_time); break
                    if self.position == 1: self.max_price_seen = max(self.max_price_seen, m_row['close'])
                    else: self.min_price_seen = min(self.min_price_seen, m_row['close'])
                if self.position == 0: continue

            if pending_maker_order and self.position == 0:
                tf_delta = pd.to_timedelta(config["SIGNAL_TIMEFRAME"])
                intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                for m_time, m_row in intra_data.iterrows():
                    # Hysteresis check for pending RETEST
                    sig_type_h, _, _ = self.check_entry_signal(row, m_row['close'], use_sniper, retest_maker, config, is_ambushing=True)
                    if sig_type_h != 'RETEST':
                        pending_maker_order = None; break

                    if (pending_maker_order['side'] == 1 and m_row['low'] <= pending_maker_order['price']) or \
                       (pending_maker_order['side'] == -1 and m_row['high'] >= pending_maker_order['price']):
                        self._open_position(pending_maker_order['side'], pending_maker_order['price'], pending_maker_order['sl'], m_time, risk_pct, is_maker=True)
                        pending_maker_order = None; break
                if pending_maker_order and (curr_time - pending_maker_order['timestamp']).total_seconds() > 14400: pending_maker_order = None

            if self.position == 0 and not pending_maker_order and curr_time > self.last_close_time:
                sig_type, target_p, sl_p = self.check_entry_signal(row, row['close'], use_sniper, retest_maker, config, is_ambushing=False)
                if sig_type == 'RETEST':
                    pending_maker_order = {'side': (1 if target_p > row['ema_h'] else -1), 'price': target_p, 'sl': sl_p, 'timestamp': curr_time}
                elif sig_type == 'SNIPER':
                    tf_delta = pd.to_timedelta(config["SIGNAL_TIMEFRAME"])
                    intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                    for m_time, m_row in intra_data.iterrows():
                        # Hysteresis check for Sniper while searching intra-bar
                        sig_type_h, _, _ = self.check_entry_signal(row, m_row['close'], use_sniper, retest_maker, config, is_ambushing=True)
                        if sig_type_h != 'SNIPER': break # Signal lost intra-bar

                        if (target_p > row['ema_h'] and m_row['high'] >= target_p) or (target_p < row['ema_h'] and m_row['low'] <= target_p):
                            self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, m_time, risk_pct, is_sniper=True); break
                elif sig_type == 'MARKET':
                    self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, curr_time, risk_pct)

            self.equity_curve.append(self.capital)
        return self.trades, self.equity_curve

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

    def run_streaming_backtest(self, df_1m, **kwargs):
        """
        Hyper-optimized streaming simulation. Pre-calculates base indicators 
        and only updates the 'active' bar using fast index access.
        """
        if df_1m.empty:
            print("❌ Error: df_1m is empty. Cannot run streaming backtest."); return [], []

        config = self.c.copy()
        mapping = {
            'vol_mult': 'VOL_MULTIPLIER',
            'atr_trail_mult': 'TRAILING_ATR_MULT',
            'risk_pct': 'RISK_PER_TRADE',
            'ema_period': 'EMA_TREND_PERIOD',
            'adx_threshold': 'ADX_FILTER_LEVEL',
            'donchian_period': 'DONCHIAN_PERIOD'
        }
        for kw, cfg_key in mapping.items():
            if kw in kwargs: config[cfg_key] = kwargs[kw]
        
        use_sniper = kwargs.get('use_sniper', False)
        retest_maker = kwargs.get('retest_maker', False)
        risk_pct = config.get("RISK_PER_TRADE", 0.02)
        
        # Ensure timestamp is datetime and sorted without using sort_values if possible
        if not pd.api.types.is_datetime64_any_dtype(df_1m['timestamp']):
            df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
        
        # Check if already sorted to avoid argsort error
        is_sorted = df_1m['timestamp'].is_monotonic_increasing
        if not is_sorted:
            try:
                df_1m = df_1m.sort_values('timestamp').reset_index(drop=True)
            except IndexError:
                print("⚠️ Warning: Pandas sorting failed. Proceeding with original order.")
        
        df_1m = df_1m.dropna(subset=['timestamp']).reset_index(drop=True)
        
        print(f"📊 Preparing simulation for {df_1m['timestamp'].min()} to {df_1m['timestamp'].max()}...")
        
        # 1. Pre-calculate ALL CLOSED 1h and 4h bars at once (Very fast)
        def get_all_base_bars(df, tf):
            resampled = df.set_index('timestamp').resample(tf).agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()
            return resampled

        df_1h_base = get_all_base_bars(df_1m, config["SIGNAL_TIMEFRAME"])
        df_4h_base = get_all_base_bars(df_1m, config["TREND_TIMEFRAME"])
        
        # Pre-calculate Indicators for all CLOSED bars (look-ahead free)
        # We shift(1) later to make sure we only see "completed" info
        df_1h_ind = self.calculate_indicators(df_1h_base, df_4h_base, config)
        
        # To simulate the "developing" bar, we need 1m data access
        # Convert to numpy for light-speed access
        m_times = df_1m['timestamp'].values.astype('datetime64[s]')
        m_closes = df_1m['close'].values
        m_highs = df_1m['high'].values
        m_lows = df_1m['low'].values
        m_vols = df_1m['volume'].values
        
        pending_maker_order = None
        self.equity_curve = []
        
        print(f"🚀 Launching Hyper-Sim ({len(df_1m)} steps)...")
        
        # We'll step through 1m data but only react if it's a significant interval
        # Step 1 minute for precision, but avoid expensive operations
        for i in range(200 * 60, len(df_1m), 1): 
            curr_time = m_times[i]
            last_price = m_closes[i]
            
            # Key Realism: At any minute 'i', we only know:
            # 1. Indicators from all bars CLOSED before curr_time
            # 2. Price/Volume from the CURRENT bar so far
            
            # Find the index of the last closed 1h bar
            # (Using binary search or simple floor logic)
            current_bar_start = curr_time.astype('datetime64[h]')
            
            # Indicators from PREVIOUS bar (completely closed)
            # Optimization: Pull from pre-calculated df_1h_ind
            prev_bar_idx = current_bar_start - np.timedelta64(1, 'h')
            
            try:
                # Get the indicator row for the bar that just CLOSED
                # Note: df_1h_ind.iloc[-1] would be the bar containing curr_time.
                # We need the one before it to avoid look-ahead bias.
                row = df_1h_ind.loc[prev_bar_idx]
            except KeyError:
                continue

            # --- 1. Position Management (using 1m tick) ---
            if self.position != 0:
                state = {'position': self.position, 'entry_price': self.entry_price, 'max_price_seen': self.max_price_seen, 'min_price_seen': self.min_price_seen, 'sl_price': self.sl_price}
                if self.check_exit_signal(row, last_price, state, config):
                    self._close_position(last_price, pd.Timestamp(curr_time))
                else:
                    if self.position == 1: self.max_price_seen = max(self.max_price_seen, last_price)
                    else: self.min_price_seen = min(self.min_price_seen, last_price)

            # --- 2. Check Pending Retest Order ---
            elif pending_maker_order:
                # Hysteresis check for pending RETEST
                sig_type_h, _, _ = self.check_entry_signal(row, last_price, use_sniper, retest_maker, config, is_ambushing=True)
                if sig_type_h != 'RETEST':
                    pending_maker_order = None
                elif (pending_maker_order['side'] == 1 and m_lows[i] <= pending_maker_order['price']) or \
                   (pending_maker_order['side'] == -1 and m_highs[i] >= pending_maker_order['price']):
                    self._open_position(pending_maker_order['side'], pending_maker_order['price'], pending_maker_order['sl'], pd.Timestamp(curr_time), risk_pct, is_maker=True)
                    pending_maker_order = None
                elif (pd.Timestamp(curr_time) - pending_maker_order['timestamp']).total_seconds() > 14400:
                    pending_maker_order = None

            # --- 3. New Signal Discovery ---
            if self.position == 0 and not pending_maker_order and pd.Timestamp(curr_time) > self.last_close_time:
                # ... (volume calculation)
                current_bar_1m_start_idx = i - (i % 60)
                current_cum_vol = np.sum(m_vols[current_bar_1m_start_idx : i+1])
                
                # Create a modified row for signal check that has current volume and current price
                live_row = row.copy()
                live_row['volume'] = current_cum_vol
                live_row['close'] = last_price
                
                # Determine is_ambushing state for SNIPER (if it was already triggered in this candle)
                # In streaming mode, we don't have active_sniper_order_id, but we can check if it just triggered.
                sig_type, target_p, sl_p = self.engine.check_entry_signal(live_row, last_price, use_sniper, retest_maker, config, is_ambushing=False)
                
                if sig_type == 'RETEST':
                    pending_maker_order = {'side': (1 if target_p > row['ema_h'] else -1), 'price': target_p, 'sl': sl_p, 'timestamp': pd.Timestamp(curr_time)}
                elif sig_type == 'SNIPER':
                    # Check again with hysteresis to see if it would have been kept if already active
                    # (This is a bit redundant for new signal, but good for consistency)
                    if (target_p > row['ema_h'] and m_highs[i] >= target_p) or (target_p < row['ema_h'] and m_lows[i] <= target_p):
                        self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_time), risk_pct, is_sniper=True)
                elif sig_type == 'MARKET':
                    # Only if bar is actually closing? 
                    # No, live bot checks on every update. 
                    # If conditions hit intra-bar, MARKET entry is executed.
                    self._open_position((1 if target_p > row['ema_h'] else -1), target_p, sl_p, pd.Timestamp(curr_time), risk_pct)

            if i % 1440 == 0: self.equity_curve.append(self.capital)
                
        return self.trades, self.equity_curve, df_1h_ind

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

