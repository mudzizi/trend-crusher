import pandas as pd
import numpy as np
from src.strategy_base import BaseStrategy
from src.config import CONFIG

class TrendCrusherMACD(BaseStrategy):
    """
    MACD Trading Strategy.
    Signal Timing:
      At the close of candle t-1, we evaluate:
      diff = MACD(t-2) - MACD(t-1)
      If diff < 0 (MACD is increasing): enter LONG at the open of candle t.
      If diff > 0 (MACD is decreasing): enter SHORT at the open of candle t.
    """
    def __init__(self, config=CONFIG):
        self.c = config.copy()
        self.capital = self.c.get("SEED", 10000.0)
        self.position = 0  # 1 for Long, -1 for Short, 0 for None
        self.entry_price = 0.0
        self.quantity = 0.0
        self.entry_fee = 0.0
        self.sl_price = 0.0
        self.last_close_time = pd.Timestamp(0)
        self.trades = []
        self.equity_curve = [self.capital]

    def calculate_indicators(self, df_sig, df_trend, config, is_live=False):
        """
        Calculates standard MACD (12, 26) indicators, ATR, ADX, Choppiness, Squeeze, and EMA filter.
        """
        from src.indicators import calculate_atr, calculate_adx, calculate_choppiness, calculate_squeeze_score
        
        df = df_sig.copy()
        
        # Calculate EMA 12 and EMA 26
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        
        # MACD line
        df['macd'] = ema_12 - ema_26
        
        # Shift values to reference past closed bars
        df['macd_prev'] = df['macd'].shift(1)      # MACD(t-1)
        df['macd_prev2'] = df['macd'].shift(2)     # MACD(t-2)
        
        # Formula: MACD(t-2) - MACD(t-1)
        df['macd_diff'] = df['macd_prev2'] - df['macd_prev']
        
        # Calculate ATR and ADX
        df['atr'] = calculate_atr(df, 14)
        df['adx'] = calculate_adx(df, 14)
        
        # Calculate Choppiness Index and Squeeze Score
        df['chop'] = calculate_choppiness(df, 14)
        df['squeeze'] = calculate_squeeze_score(df, 20, 20)
        
        # Calculate EMA Filter
        ema_span = self.c.get('EMA_FILTER_SPAN', 200)
        df['ema_filter'] = df['close'].ewm(span=ema_span, adjust=False).mean()
        
        # Shift to reference closed bars
        df['atr_prev'] = df['atr'].shift(1)
        df['adx_prev'] = df['adx'].shift(1)
        df['chop_prev'] = df['chop'].shift(1)
        df['squeeze_prev'] = df['squeeze'].shift(1)
        df['ema_filter_prev'] = df['ema_filter'].shift(1)
        df['close_prev'] = df['close'].shift(1)
        
        return df

    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None, is_ambushing=False):
        """
        Required by BaseStrategy interface.
        Evaluates entry filters (ADX, CHOP, Squeeze, EMA Filter) and MACD crossover.
        """
        macd_diff = row.get('macd_diff', 0.0)
        if pd.isna(macd_diff) or macd_diff == 0.0:
            return None, None, None
        
        c = config if config else self.c
        
        # ADX trend strength filter
        adx_val = row.get('adx_prev', 0.0)
        adx_threshold = c.get('ADX_THRESHOLD', 0.0)
        is_trending = (adx_threshold == 0.0) or (not pd.isna(adx_val) and adx_val >= adx_threshold)
        
        # Choppiness Index filter
        chop_val = row.get('chop_prev', 0.0)
        chop_threshold = c.get('CHOP_THRESHOLD', 0.0)
        is_not_choppy = (chop_threshold == 0.0) or (not pd.isna(chop_val) and chop_val < chop_threshold)
        
        # Volatility Squeeze filter
        squeeze_val = row.get('squeeze_prev', 0.0)
        use_squeeze = c.get('USE_SQUEEZE_FILTER', False)
        is_not_squeezed = (not use_squeeze) or (not pd.isna(squeeze_val) and squeeze_val == 0.0)
        
        allow_entry = is_trending and is_not_choppy and is_not_squeezed
        if not allow_entry:
            return None, None, None
            
        # EMA Trend filter
        use_ema = c.get('USE_EMA_FILTER', False)
        ema_filter_val = row.get('ema_filter_prev', 0.0)
        close_prev = row.get('close_prev', 0.0)
        
        # Negative diff: MACD(t-2) < MACD(t-1) -> Long
        if macd_diff < 0:
            if use_ema and not pd.isna(ema_filter_val) and ema_filter_val > 0.0:
                if close_prev < ema_filter_val:
                    return None, None, None
            return 'MARKET', last_price, None
        # Positive diff: MACD(t-2) > MACD(t-1) -> Short
        else:
            if use_ema and not pd.isna(ema_filter_val) and ema_filter_val > 0.0:
                if close_prev > ema_filter_val:
                    return None, None, None
            return 'MARKET', last_price, None

    def check_exit_signal(self, row, last_price, state, config):
        """
        Required by BaseStrategy interface.
        """
        # Since this is a reversing strategy, exits are handled by entry signals of opposite directions.
        return False

    def run_streaming_backtest(self, df_input, **kwargs):
        """
        Overridden backtest engine specifically for the MACD candle-level strategy.
        Accepts either 1m data (and resamples it) or pre-resampled 1h/4h data directly.
        """
        from src.strategy import get_all_base_bars
        
        timeframe = kwargs.get('timeframe', self.c.get('SIGNAL_TIMEFRAME', '1h'))
        
        # Determine if input is 1m or already the target timeframe
        if len(df_input) > 1:
            first_diff_mins = (df_input['timestamp'].iloc[1] - df_input['timestamp'].iloc[0]).total_seconds() / 60.0
            is_already_resampled = False
            if timeframe == '1h' and abs(first_diff_mins - 60.0) < 5.0:
                is_already_resampled = True
            elif timeframe == '4h' and abs(first_diff_mins - 240.0) < 5.0:
                is_already_resampled = True
                
            if is_already_resampled:
                df_sig = df_input.copy()
            else:
                df_sig = get_all_base_bars(df_input, timeframe, include_incomplete=False)
        else:
            df_sig = get_all_base_bars(df_input, timeframe, include_incomplete=False)
            
        # Calculate indicators
        df_sig = self.calculate_indicators(df_sig, None, self.c)
        
        # Reset state
        self.capital = self.c.get('SEED', 10000.0)
        self.position = 0
        self.entry_price = 0.0
        self.quantity = 0.0
        self.entry_fee = 0.0
        self.sl_price = 0.0
        self.trades = []
        self.equity_curve = [self.capital]
        
        for idx in range(2, len(df_sig)):
            row = df_sig.iloc[idx]
            macd_diff = row['macd_diff']
            
            timestamp = row['timestamp']
            open_price = row['open']
            high_price = row['high']
            low_price = row['low']
            
            # 1. Check MACD signal at candle open
            sig_t, _, _ = self.check_entry_signal(row, open_price)
            
            if not pd.isna(macd_diff) and macd_diff != 0.0:
                # Negative diff -> Long signal
                if macd_diff < 0:
                    if self.position == -1:
                        self._close_position(open_price, timestamp)
                    if sig_t == 'MARKET' and self.position == 0:
                        self._open_position(1, open_price, timestamp, atr_val=row.get('atr_prev', 0.0))
                # Positive diff -> Short signal
                elif macd_diff > 0:
                    if self.position == 1:
                        self._close_position(open_price, timestamp)
                    if sig_t == 'MARKET' and self.position == 0:
                        self._open_position(-1, open_price, timestamp, atr_val=row.get('atr_prev', 0.0))
            
            # 2. Check Stop Loss during the candle
            if self.position == 1 and self.sl_price > 0.0:
                if low_price <= self.sl_price:
                    self._close_position(self.sl_price, timestamp, exit_type='SL')
            elif self.position == -1 and self.sl_price > 0.0:
                if high_price >= self.sl_price:
                    self._close_position(self.sl_price, timestamp, exit_type='SL')
            
            self.equity_curve.append(self.capital)
            
        return self.trades, self.equity_curve, df_sig

    def _open_position(self, side, price, timestamp, atr_val=0.0):
        e_p = price
        # Slippage: 0.05% for market orders
        slip = e_p * 0.0005 
        e_p = e_p + slip if side == 1 else e_p - slip
        
        self.position = side
        self.entry_price = e_p
        
        # Size: 1.0x leverage (100% of current capital)
        self.quantity = self.capital / e_p
        
        # Taker fee: 0.05%
        fee_r = 0.0005
        self.entry_fee = e_p * self.quantity * fee_r
        
        # Stop loss setup
        atr_mult = self.c.get('ATR_SL_MULT', 0.0)
        sl_pct = self.c.get('STOP_LOSS_PCT', 0.0)
        
        if atr_mult > 0.0 and atr_val > 0.0:
            self.sl_price = e_p - (atr_val * atr_mult) if side == 1 else e_p + (atr_val * atr_mult)
        elif sl_pct > 0.0:
            self.sl_price = e_p * (1.0 - sl_pct) if side == 1 else e_p * (1.0 + sl_pct)
        else:
            self.sl_price = 0.0
            
        self.trades.append({
            'time': timestamp,
            'side': 'LONG' if side == 1 else 'SHORT',
            'type': 'OPEN',
            'price': e_p,
            'quantity': self.quantity
        })

    def _close_position(self, price, timestamp, exit_type='CLOSE'):
        e_p = price
        # Slippage: 0.05% for market orders
        slip = e_p * 0.0005
        e_p = e_p - slip if self.position == 1 else e_p + slip
        
        # Taker fee: 0.05%
        fee_r = 0.0005
        ex_f = e_p * self.quantity * fee_r
        
        pnl = (e_p - self.entry_price) * self.quantity * self.position
        net_pnl = pnl - (self.entry_fee + ex_f)
        
        self.capital += net_pnl
        self.trades.append({
            'time': timestamp,
            'side': 'LONG' if self.position == 1 else 'SHORT',
            'type': exit_type,
            'price': e_p,
            'pnl': net_pnl,
            'pnl_usdt': net_pnl
        })
        
        self.position = 0
        self.entry_price = 0.0
        self.quantity = 0.0
        self.entry_fee = 0.0
        self.sl_price = 0.0
        self.last_close_time = timestamp
