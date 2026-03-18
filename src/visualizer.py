import matplotlib
matplotlib.use('Agg') # 서버 환경을 위한 비대화형 백엔드 설정
import matplotlib.pyplot as plt
import pandas as pd
import os

class TradingVisualizer:
    def __init__(self, report_dir="reports"):
        self.report_dir = report_dir
        os.makedirs(report_dir, exist_ok=True)
        os.makedirs("static", exist_ok=True)

    def generate_report(self, df_ohlcv, trades_df, equity_df, symbol):
        plt.style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [3, 1]})
        
        # Ensure timestamps are datetime objects for matplotlib
        df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'])
        
        ax1.plot(df_ohlcv['timestamp'], df_ohlcv['close'], label='Price', color='white', alpha=0.6)
        if 'upper' in df_ohlcv.columns:
            ax1.plot(df_ohlcv['timestamp'], df_ohlcv['upper'], label='Upper Donchian', color='cyan', linestyle='--', alpha=0.4)
            ax1.plot(df_ohlcv['timestamp'], df_ohlcv['lower'], label='Lower Donchian', color='orange', linestyle='--', alpha=0.4)
        if 'ema_h' in df_ohlcv.columns:
            ax1.plot(df_ohlcv['timestamp'], df_ohlcv['ema_h'], label='Trend EMA', color='yellow', alpha=0.5)

        for _, trade in trades_df.iterrows():
            o_time = pd.to_datetime(trade['open_time'])
            c_time = pd.to_datetime(trade['close_time'])
            ax1.scatter(o_time, trade['open_price'], marker='^' if trade['side'] == 'LONG' else 'v', 
                        color='lime' if trade['side'] == 'LONG' else 'red', s=100, zorder=5)
            ax1.scatter(c_time, trade['close_price'], marker='x', color='white', s=80, zorder=5)
            ax1.plot([o_time, c_time], [trade['open_price'], trade['close_price']], 
                     color='lime' if trade['pnl_pct'] > 0 else 'red', alpha=0.3, linestyle=':')

        ax1.set_title(f"{symbol} Trading Report", fontsize=16)
        ax1.legend()
        ax1.grid(alpha=0.2)

        if not equity_df.empty:
            equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
            ax2.plot(equity_df['timestamp'], equity_df['balance'], color='lime', label='Equity (USDT)')
            ax2.fill_between(equity_df['timestamp'], equity_df['balance'], equity_df['balance'].iloc[0], 
                             color='lime', alpha=0.1)
            total_ret = ((equity_df['balance'].iloc[-1] / equity_df['balance'].iloc[0]) - 1) * 100
            ax2.set_title(f"Cumulative Return: {total_ret:+.2f}%", loc='right', color='lime')

        ax2.set_ylabel("Capital")
        ax2.grid(alpha=0.2)
        ax2.legend()

        plt.tight_layout()
        filename = f"{self.report_dir}/report_{symbol.replace('/', '_')}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(filename)
        plt.close(fig) # 메모리 해제를 위해 fig 객체 명시적 종료
        return filename

    def generate_market_view(self, df_ohlcv, symbol):
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(15, 7))
        df = df_ohlcv.tail(100)
        
        ax.plot(df['timestamp'], df['close'], label='Price', color='white', linewidth=2)
        ax.plot(df['timestamp'], df['upper'], label='Upper (Breakout)', color='cyan', linestyle='--', alpha=0.6)
        ax.plot(df['timestamp'], df['lower'], label='Lower (Breakdown)', color='orange', linestyle='--', alpha=0.6)
        ax.plot(df['timestamp'], df['ema_h'], label='Trend EMA (4H)', color='yellow', linewidth=1.5, alpha=0.8)
        
        curr_price = df['close'].iloc[-1]
        ax.axhline(curr_price, color='lime', linestyle=':', alpha=0.5)
        
        ax.set_title(f"Live Market Insight: {symbol}", fontsize=16)
        ax.legend(loc='upper left')
        ax.grid(alpha=0.1)
        
        plt.tight_layout()
        filename = "static/current_market.png"
        plt.savefig(filename)
        plt.close(fig) # 메모리 해제
        return filename
