import pandas as pd
import numpy as np
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx, calculate_choppiness, calculate_chaos_index, calculate_squeeze_score
from src.config import CONFIG
from src.strategy_base import BaseStrategy
from src.strategy_numba import numba_check_entry, numba_check_exit, numba_find_first_exit

def get_all_base_bars(df_1m, timeframe, include_incomplete=False):
    df_1m = df_1m.copy()
    df_1m.set_index('timestamp', inplace=True)
    resampled = df_1m.resample(timeframe).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    })
    if not include_incomplete: resampled = resampled.dropna()
    return resampled.reset_index()

class TrendCrusherV2(BaseStrategy):
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
        
        triggered, new_sl = numba_check_exit(
            last_price, state['position'], state['entry_price'], state['max_price_seen'], state['min_price_seen'], state['sl_price'],
            row['atr'], config.get("TRAILING_ATR_MULT", 3.0), config.get("USE_ADAPTIVE_TRAIL", False), steps_arr, config.get("BE_GUARD_THRESHOLD", 0.0)
        )
        
        # Update state so live bot picks up the new protected SL
        state['sl_price'] = new_sl
        return triggered

    def run_streaming_backtest(self, df_1m, **kwargs):
        from src.backtest_engine import BacktestEngine
        engine = BacktestEngine(self)
        return engine.run(df_1m, **kwargs)

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
