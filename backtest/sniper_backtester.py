import pandas as pd
import numpy as np
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.strategy import TrendCrusherV2
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_atr, calculate_avg_vol, calculate_adx
from src.visualizer import TradingVisualizer

class SniperBacktester(TrendCrusherV2):
    """
    Extends TrendCrusherV2 to simulate the economic effect of the Sniper (Limit-First) entry.
    """
    def __init__(self, config=CONFIG):
        super().__init__(config)
        self.maker_fee = 0.0002 # Assume lower maker fee (Binance standard)
        self.taker_fee = config.get("FEE_RATE", 0.0004)
        self.sniper_proximity = config.get("SNIPER_PROXIMITY_PCT", 0.005)
        self.sniper_success_count = 0
        self.sniper_fail_count = 0

    def _open_position_sniper(self, direction, target_price, atr, timestamp, risk_pct, intra_data):
        side = 'LONG' if direction == 1 else 'SHORT'
        
        # 1. Evaluate if Sniper Ambush was successful
        was_successful = False
        if not intra_data.empty:
            breakout_open = intra_data.iloc[0]['open']
            dist = abs(breakout_open - target_price) / breakout_open
            if dist <= self.sniper_proximity:
                was_successful = True
        
        # 2. Apply differentiated costs
        if was_successful:
            self.entry_price = target_price # ZERO slippage
            current_fee = self.maker_fee
            self.sniper_success_count += 1
            entry_type = "SNIPER_LIMIT"
        else:
            slippage = self.c.get("SLIPPAGE", 0.0005)
            self.entry_price = target_price * (1 + slippage) if direction == 1 else target_price * (1 - slippage)
            current_fee = self.taker_fee
            self.sniper_fail_count += 1
            entry_type = "MARKET_TAKER"

        self.sl_price = target_price - (atr * self.c["INITIAL_SL_ATR"]) if direction == 1 else target_price + (atr * self.c["INITIAL_SL_ATR"])
        self.quantity = self.calculate_position_size(self.entry_price, self.sl_price, risk_pct)
        
        if self.quantity > 0:
            self.capital -= self.entry_price * self.quantity * current_fee
            self.position = direction
            self.max_price_seen = self.entry_price
            self.min_price_seen = self.entry_price
            self.trades.append({
                'time': timestamp, 
                'type': 'OPEN', 
                'entry_mode': entry_type,
                'side': side, 
                'price': self.entry_price,
                'qty': self.quantity
            })

    def run_sniper_backtest(self, df_sig, df_trend, df_check):
        df = df_sig.copy()
        df['upper'], df['lower'] = calculate_donchian(df, period=self.c["DONCHIAN_PERIOD"])
        df['atr'] = calculate_atr(df, period=14)
        df['avg_vol'] = calculate_avg_vol(df, period=20)
        df['adx'] = calculate_adx(df, period=14)
        
        ema_vals = calculate_ema(df_trend, period=self.c["EMA_TREND_PERIOD"])
        df_h = pd.DataFrame({'timestamp': df_trend['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df = df.join(df_h, on='timestamp').ffill()
        
        df_check_idx = df_check.set_index(pd.to_datetime(df_check['timestamp']))
        
        for i in range(max(self.c["DONCHIAN_PERIOD"], 1), len(df)):
            row = df.iloc[i]
            curr_time = pd.to_datetime(row['timestamp'])
            if curr_time not in df_check_idx.index: continue
            
            if self.position != 0:
                tf_delta = pd.to_timedelta(self.c["SIGNAL_TIMEFRAME"])
                try: intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                except KeyError: intra_data = pd.DataFrame()

                closed = False
                for m_time, m_row in intra_data.iterrows():
                    m_close = m_row['close']
                    curr_atr_mult = self.c["TRAILING_ATR_MULT"]
                    if self.c.get("USE_ADAPTIVE_TRAIL", False):
                        pnl_now = ((m_close / self.entry_price) - 1) * 100 * self.position
                        for step in self.c.get("ADAPTIVE_TRAIL_STEPS", []):
                            if pnl_now >= step['pnl_pct']:
                                curr_atr_mult = min(curr_atr_mult, step['atr_mult'])

                    if self.position == 1:
                        self.max_price_seen = max(self.max_price_seen, m_close)
                        trail_sl = self.max_price_seen - (row['atr'] * curr_atr_mult)
                        if m_close <= trail_sl or m_close <= self.sl_price:
                            self._close_position(m_close, m_time); closed = True; break
                    else:
                        self.min_price_seen = min(self.min_price_seen, m_close)
                        trail_sl = self.min_price_seen + (row['atr'] * curr_atr_mult)
                        if m_close >= trail_sl or m_close >= self.sl_price:
                            self._close_position(m_close, m_time); closed = True; break
                if closed: continue

            if self.position == 0 and curr_time > self.last_close_time:
                is_vol_burst = row['volume'] > (row['avg_vol'] * self.c["VOL_MULTIPLIER"])
                is_trending = row['adx'] > self.c["ADX_FILTER_LEVEL"]

                if is_vol_burst and is_trending and row['close'] > row['ema_h']:
                    target_level = row['upper']
                    if row['close'] > target_level:
                        tf_delta = pd.to_timedelta(self.c["SIGNAL_TIMEFRAME"])
                        try:
                            intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                            breakout_bars = intra_data[intra_data['high'] >= target_level]
                            if not breakout_bars.empty:
                                breakout_time = breakout_bars.index[0]
                                self._open_position_sniper(1, target_level, row['atr'], breakout_time, self.c["RISK_PER_TRADE"], intra_data.loc[:breakout_time])
                        except: pass
                elif is_vol_burst and is_trending and row['close'] < row['ema_h']:
                    target_level = row['lower']
                    if row['close'] < target_level:
                        tf_delta = pd.to_timedelta(self.c["SIGNAL_TIMEFRAME"])
                        try:
                            intra_data = df_check_idx.loc[curr_time : curr_time + tf_delta]
                            breakout_bars = intra_data[intra_data['low'] <= target_level]
                            if not breakout_bars.empty:
                                breakout_time = breakout_bars.index[0]
                                self._open_position_sniper(-1, target_level, row['atr'], breakout_time, self.c["RISK_PER_TRADE"], intra_data.loc[:breakout_time])
                        except: pass

            self.equity_curve.append(self.capital)
        return self.trades, self.equity_curve

def run_comparison(symbol):
    clean_sym = symbol.replace('/', '_')
    df_sig = pd.read_csv(f"data/{clean_sym}_1h.csv")
    df_trend = pd.read_csv(f"data/{clean_sym}_4h.csv")
    df_check = pd.read_csv(f"data/{clean_sym}_1m.csv")
    
    # Common Config Base
    base_config = CONFIG.copy()
    if symbol in CONFIG["SYMBOL_SETTINGS"]:
        base_config.update(CONFIG["SYMBOL_SETTINGS"][symbol])
    
    for key in ["FEE_RATE", "SLIPPAGE", "SEED", "DONCHIAN_PERIOD", "VOL_MULTIPLIER", "TRAILING_ATR_MULT", "ADX_FILTER_LEVEL", "EMA_TREND_PERIOD", "SIGNAL_TIMEFRAME", "RISK_PER_TRADE", "INITIAL_SL_ATR"]:
        if key not in base_config:
            base_config[key] = CONFIG[key]

    # --- Setup Structured Directories ---
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    base_dir = f"reports/{clean_sym}"
    sniper_report_dir = f"{base_dir}/Sniper_Mode/{timestamp}"
    market_report_dir = f"{base_dir}/Market_Mode/{timestamp}"
    
    os.makedirs(sniper_report_dir, exist_ok=True)
    os.makedirs(market_report_dir, exist_ok=True)

    # 1. Classic Market Mode (0.5% Slippage)
    config_market = base_config.copy()
    config_market["SLIPPAGE"] = 0.005 
    tester_m = TrendCrusherV2(config=config_market)
    trades_m, curve_m = tester_m.run_precision_backtest(df_sig, df_trend, df_check)
    ret_m = ((curve_m[-1] / config_market["SEED"]) - 1) * 100
    
    # 2. Sniper Mode (Intra-bar Simulation)
    tester_s = SniperBacktester(config=base_config)
    trades_s, curve_s = tester_s.run_sniper_backtest(df_sig, df_trend, df_check)
    ret_s = ((curve_s[-1] / base_config["SEED"]) - 1) * 100
    
    print(f"\n>>> Comparison for {symbol} <<<")
    print(f"Classic Market Mode (0.5% Slip): {ret_m:>8.2f}%")
    print(f"Sniper Mode (Maker/Limit):      {ret_s:>8.2f}%")
    success_rate = (tester_s.sniper_success_count / (tester_s.sniper_success_count + tester_s.sniper_fail_count + 1e-6)) * 100
    print(f"Sniper Success Rate:            {success_rate:.1f}%")
    print(f"Alpha Gained:                   {ret_s - ret_m:>8.2f}%")

    # --- Helper: Save Raw Data ---
    def save_raw_trades(trades, path):
        if not trades: return
        df = pd.DataFrame(trades)
        rows = []
        for i in range(0, len(df), 2):
            if i+1 >= len(df): break
            o = df.iloc[i]; c = df.iloc[i+1]
            rows.append({
                'open_time': o['time'], 'close_time': c['time'],
                'side': o['side'], 'entry_mode': o.get('entry_mode', 'MARKET'),
                'open_price': o['price'], 'close_price': c['price'],
                'pnl_usdt': c['pnl_usdt'], 'pnl_pct': ((c['price']/o['price'])-1)*100*(1 if o['side']=='LONG' else -1)
            })
        pd.DataFrame(rows).to_csv(f"{path}/trades.csv", index=False)

    save_raw_trades(trades_s, sniper_report_dir)
    save_raw_trades(trades_m, market_report_dir)
    
    # --- Helper: Generate Graphs ---
    def generate_chart(trades, curve, path, title):
        viz = TradingVisualizer(report_dir=path)
        df_ohlcv = df_sig.copy()
        upper, lower = calculate_donchian(df_ohlcv, base_config["DONCHIAN_PERIOD"])
        df_ohlcv['upper'], df_ohlcv['lower'] = upper, lower
        ema_vals = calculate_ema(df_trend, base_config["EMA_TREND_PERIOD"])
        df_h = pd.DataFrame({'timestamp': df_trend['timestamp'], 'ema_h': ema_vals}).set_index('timestamp')
        df_ohlcv = df_ohlcv.join(df_h, on='timestamp').ffill()

        df_trades_formatted = pd.DataFrame()
        if trades:
            rows = []
            for i in range(0, len(trades), 2):
                if i+1 >= len(trades): break
                o = trades[i]; c = trades[i+1]
                rows.append({
                    'open_time': o['time'], 'close_time': c['time'],
                    'side': o['side'], 'open_price': o['price'], 'close_price': c['price'],
                    'pnl_pct': ((c['price']/o['price'])-1)*100*(1 if o['side']=='LONG' else -1)
                })
            df_trades_formatted = pd.DataFrame(rows)

        equity_df = pd.DataFrame({'timestamp': df_sig['timestamp'][:len(curve)], 'balance': curve})
        viz.generate_report(df_ohlcv, df_trades_formatted, equity_df, title)

    generate_chart(trades_s, curve_s, sniper_report_dir, f"{symbol} (Sniper Mode)")
    generate_chart(trades_m, curve_m, market_report_dir, f"{symbol} (Market Mode)")
    
    print(f"Results organized in: reports/{clean_sym}/")

if __name__ == "__main__":
    symbols = ["TRUMP/USDT", "ETH/USDT", "XRP/USDT", "XAU/USDT"]
    for sym in symbols:
        run_comparison(sym)
