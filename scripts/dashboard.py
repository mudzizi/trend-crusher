from flask import Flask, render_template, send_from_directory
from src.db_manager import DBManager
from src.visualizer import TradingVisualizer
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_avg_vol, calculate_adx
import os
import pandas as pd
import ccxt
import traceback
import time

# --- Flask Setup ---
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(os.path.dirname(base_dir), 'templates')
static_dir = os.path.join(os.path.dirname(base_dir), 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
db = DBManager()
viz = TradingVisualizer()
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

@app.route('/')
def index():
    symbols = CONFIG.get("SYMBOLS_LIST", [CONFIG["SYMBOL"]])
    market_summaries = []
    active_positions = []
    error_msg = None
    
    try:
        # 1. Fetch Active Positions from DB
        active_df = db.get_active_trades()
        for _, pos in active_df.iterrows():
            sym = pos['symbol']
            ticker = exchange.fetch_ticker(sym)
            curr_price = float(ticker['last'])
            
            pnl_pct = ((curr_price / pos['open_price']) - 1) * 100
            if pos['side'] == 'SHORT':
                pnl_pct = -pnl_pct
                
            # SL Status Calculation
            # We need to estimate current SL since it's not in DB yet (it's managed in-memory by the bot)
            # But for the dashboard, we'll show distance to initial SL and entry
            # To be more accurate, the bot should ideally log SL to DB, but for now we'll calculate basic distance
            
            active_positions.append({
                "symbol": sym,
                "side": pos['side'],
                "entry": pos['open_price'],
                "curr": curr_price,
                "qty": pos['quantity'],
                "pnl": round(pnl_pct, 2),
                "open_time": pos['open_time']
            })

        # 2. Fetch Market Summary for all watched symbols
        for sym in symbols:
            try:
                ticker = exchange.fetch_ticker(sym)
                c_close = float(ticker['last'])
                
                # Summary info for the list
                market_summaries.append({
                    "symbol": sym,
                    "price": c_close,
                    "weight": CONFIG.get("SYMBOL_WEIGHTS", {}).get(sym, 1.0/len(symbols))
                })
            except:
                continue

    except Exception as e:
        error_msg = f"Dashboard Error: {str(e)}"
        print(traceback.format_exc())

    # 3. Portfolio Overall Stats
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
    
    # Calculate Win Rate
    win_rate = 0
    if len(trades_list) > 0:
        wins = len([t for t in trades_list if t['pnl_usdt'] > 0])
        win_rate = (wins / len(trades_list)) * 100

    return render_template('index.html', 
                           symbols=symbols,
                           market_summaries=market_summaries,
                           active_positions=active_positions,
                           error=error_msg,
                           trades=trades_list,
                           balance=current_balance,
                           total_return=total_return,
                           win_rate=round(win_rate, 1))

@app.route('/static/<filename>')
def serve_static(filename):
    return send_from_directory("static", filename)

@app.route('/reports/<filename>')
def serve_report(filename):
    return send_from_directory("reports", filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
