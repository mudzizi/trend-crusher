from flask import Flask, render_template, send_from_directory
from src.db_manager import DBManager
from src.visualizer import TradingVisualizer
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_avg_vol, calculate_adx
import os
import pandas as pd
import ccxt
import traceback

app = Flask(__name__)
db = DBManager()
viz = TradingVisualizer()
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

@app.route('/')
def index():
    symbol = CONFIG["SYMBOL"]
    market_stats = None
    error_msg = None
    
    try:
        # 1. Fetch Latest Market Data
        ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=100)
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
        
        # EMA 200을 위해 충분한 데이터를 가져옴 (최대 500개)
        ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=500)
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 데이터 개수 체크
        if len(df_4h) < 20:
            error_msg = f"Insufficient data for {symbol}. Need more history."
        else:
            # Calculate Indicators
            df_1h['upper'], df_1h['lower'] = calculate_donchian(df_1h, CONFIG["DONCHIAN_PERIOD"])
            df_1h['avg_vol'] = calculate_avg_vol(df_1h, CONFIG["AVG_VOL_PERIOD"])
            
            # EMA 계산 (데이터가 부족하면 있는 만큼만 계산하도록 처리됨)
            ema_period = min(len(df_4h), CONFIG["EMA_TREND_PERIOD"])
            ema_4h = calculate_ema(df_4h, period=ema_period)
            df_1h['ema_h'] = ema_4h.iloc[-1]
            
            # Generate Market View Image
            viz.generate_market_view(df_1h, symbol)
            
            last_row = df_1h.iloc[-1]
            curr_price = last_row['close']
            vol_mult = last_row['volume'] / (last_row['avg_vol'] + 1e-10)
            dist_upper = (last_row['upper'] - curr_price) / curr_price * 100
            dist_lower = (curr_price - last_row['lower']) / curr_price * 100
            trend = "BULLISH" if curr_price > last_row['ema_h'] else "BEARISH"
            
            market_stats = {
                "price": curr_price,
                "trend": trend,
                "vol_mult": round(vol_mult, 2),
                "dist_upper": round(dist_upper, 2),
                "dist_lower": round(dist_lower, 2)
            }
    except Exception as e:
        error_msg = f"API/Calculation Error: {str(e)}"
        print(traceback.format_exc())

    # 2. Database Info
    trades_df = db.get_trade_history()
    trades_list = trades_df.sort_values(by='id', ascending=False).to_dict(orient='records') if not trades_df.empty else []
    
    equity_df = db.get_equity_history()
    if not equity_df.empty:
        current_balance = equity_df['balance'].iloc[-1]
        initial_balance = equity_df['balance'].iloc[0]
        total_return = ((current_balance / initial_balance) - 1) * 100
    else:
        current_balance = CONFIG["SEED"]
        total_return = 0
    
    report_files = sorted([f for f in os.listdir("reports") if f.endswith('.png')], reverse=True) if os.path.exists("reports") else []
    
    return render_template('index.html', 
                           symbol=symbol,
                           market=market_stats,
                           error=error_msg,
                           trades=trades_list,
                           balance=current_balance,
                           total_return=total_return,
                           reports=report_files)

@app.route('/static/<filename>')
def serve_static(filename):
    return send_from_directory("static", filename)

@app.route('/reports/<filename>')
def serve_report(filename):
    return send_from_directory("reports", filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
