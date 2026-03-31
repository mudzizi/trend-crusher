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
import logging

# --- Logger Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask Setup ---
base_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(base_dir)
template_dir = os.path.join(project_root, 'templates')
static_dir = os.path.join(project_root, 'static')
reports_dir = os.path.join(project_root, 'reports')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
db = DBManager()
viz = TradingVisualizer()
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

@app.route('/')
def index():
    symbols = CONFIG.get("SYMBOLS_LIST", [CONFIG["SYMBOL"]])
    market_summaries = []
    active_positions = []
    live_monitors = [] # Initialize outside try
    error_msg = None
    
    try:
        # 1. Fetch Active Positions from DB + Bot State
        active_df = db.get_active_trades()
        for _, pos in active_df.iterrows():
            sym = pos['symbol']
            try:
                ticker = exchange.fetch_ticker(sym)
                curr_price = float(ticker['last'])
            except: curr_price = 0
            
            # Fetch Bot State for SL/Trail info
            state = db.get_bot_state(sym)
            sl_price = 0.0
            if state:
                sl_price = float(state.get('sl_price', 0.0))
            
            pnl_pct = 0
            if pos['open_price'] > 0:
                pnl_pct = ((curr_price / pos['open_price']) - 1) * 100
                if pos['side'] == 'SHORT': pnl_pct = -pnl_pct
                
            active_positions.append({
                "symbol": sym,
                "side": pos['side'],
                "entry": float(pos['open_price']),
                "curr": curr_price,
                "qty": float(pos['quantity']),
                "pnl": round(float(pnl_pct), 2),
                "open_time": pos['open_time'],
                "sl": sl_price
            })

        # 2. Fetch Live Monitoring Data
        try:
            live_status_df = db.get_all_live_status()
            for _, row in live_status_df.iterrows():
                sym = row['symbol']
                sym_settings = CONFIG.get("SYMBOL_SETTINGS", {}).get(sym, {})
                
                # Fetch hourly history for charting (last 48h)
                hist_df = db.get_history_1h(sym, limit=48)
                
                live_monitors.append({
                    "symbol": sym,
                    "vol_ratio": round(row['vol_ratio'] * 100, 1),
                    "adx_ratio": round(row['adx_ratio'] * 100, 1),
                    "adx_value": round(row['adx_value'], 1) if 'adx_value' in row else 0,
                    "prox_ratio": round(row['prox_ratio'] * 100, 1),
                    "trend_ok": bool(row['trend_ok']),
                    "score": round(row['signal_score'], 1),
                    "price": row['last_price'],
                    "upper": row['upper_band'],
                    "lower": row['lower_column'],
                    "mode": "Sniper" if sym_settings.get("USE_SNIPER", CONFIG.get("USE_SNIPER")) else ("Retest" if sym_settings.get("USE_RETEST_MAKER", CONFIG.get("USE_RETEST_MAKER")) else "Market"),
                    "vol_mult": sym_settings.get("VOL_MULTIPLIER", CONFIG.get("VOL_MULTIPLIER", 2.0)),
                    "adx_limit": sym_settings.get("ADX_FILTER_LEVEL", CONFIG.get("ADX_FILTER_LEVEL", 25.0)),
                    "history": {
                        "prices": hist_df['close'].tolist(),
                        "ema": hist_df['ema'].tolist(),
                        "upper": hist_df['donchian_upper'].tolist(),
                        "lower": hist_df['donchian_lower'].tolist(),
                        "volume": hist_df['volume'].tolist(),
                        "adx": hist_df['adx'].tolist(),
                        "labels": [str(t).split(' ')[1][:5] if ' ' in str(t) else str(t) for t in hist_df['timestamp'].tolist()]
                    }
                })
        except Exception as e:
            logger.error(f"Error fetching live status history: {e}")

        # --- [NEW] Sort monitors by symbol to keep consistent order ---
        live_monitors = sorted(live_monitors, key=lambda x: x['symbol'])

        # 3. Fetch Market Summary
        for sym in symbols:
            try:
                ticker = exchange.fetch_ticker(sym)
                market_summaries.append({
                    "symbol": sym,
                    "price": float(ticker['last']),
                    "change": float(ticker.get('percentage', 0)),
                    "weight": CONFIG.get("SYMBOL_WEIGHTS", {}).get(sym, 1.0/len(symbols))
                })
            except: continue

    except Exception as e:
        error_msg = f"Dashboard Error: {str(e)}"
        print(traceback.format_exc())

    # 3. Portfolio & History Data
    trades_df = db.get_trade_history()
    trades_list = trades_df.sort_values(by='id', ascending=False).to_dict(orient='records') if not trades_df.empty else []
    
    # Use symbol='TOTAL' for main dashboard balance and chart
    equity_df = db.get_equity_history(symbol='TOTAL')
    chart_data = {
        "labels": equity_df['timestamp'].tolist() if not equity_df.empty else [],
        "equity_values": equity_df['balance'].tolist() if not equity_df.empty else []
    }

    # Performance Stats
    win_rate = 0
    total_pnl = 0
    if len(trades_list) > 0:
        wins = [t for t in trades_list if t['pnl_pct'] > 0]
        win_rate = (len(wins) / len(trades_list)) * 100
        total_pnl = sum([t['pnl_usdt'] for t in trades_list])

    # 4. Fetch Backtest Reports (Recursive Scan)
    backtest_reports = []
    if os.path.exists(reports_dir):
        for root, dirs, files in os.walk(reports_dir):
            for f in files:
                if f.endswith(".csv") or f.endswith(".txt") or f.endswith(".png"):
                    f_path = os.path.join(root, f)
                    stats = os.stat(f_path)
                    
                    # Create a display name that shows the folder context
                    rel_path = os.path.relpath(f_path, reports_dir)
                    
                    f_type = "Trade Log" if "trades" in f else ("Equity" if "equity" in f else ("Summary" if f.endswith(".txt") else "Visual Chart"))
                    
                    backtest_reports.append({
                        "name": rel_path,
                        "date": time.strftime('%m-%d %H:%M', time.localtime(stats.st_mtime)),
                        "size": f"{stats.st_size / 1024:.1f} KB",
                        "type": f_type
                    })
        
        # Sort by date (newest first)
        backtest_reports = sorted(backtest_reports, key=lambda x: x['date'], reverse=True)

    return render_template('index.html', 
                           version=CONFIG.get("VERSION", "N/A"),
                           symbols=symbols,
                           market_summaries=market_summaries,
                           active_positions=active_positions,
                           error=error_msg,
                           trades=trades_list,
                           balance=equity_df['balance'].iloc[-1] if not equity_df.empty else CONFIG["SEED"],
                           total_return=total_pnl,
                           win_rate=round(win_rate, 1),
                           chart_data=chart_data,
                           backtest_reports=backtest_reports,
                           live_monitors=live_monitors)

@app.route('/static/<filename>')
def serve_static(filename):
    return send_from_directory(static_dir, filename)

@app.route('/reports/<path:filename>')
def serve_report(filename):
    # Security: Normalize path and prevent Path Traversal
    # 1. Get absolute paths
    target_path = os.path.abspath(os.path.join(reports_dir, filename))
    base_path = os.path.abspath(reports_dir)
    
    # 2. Strict validation: Ensure target is within reports directory
    if not target_path.startswith(base_path):
        return "Access Denied: Invalid Path", 403
    
    # 3. Verify file existence
    if not os.path.isfile(target_path):
        return "File Not Found", 404
        
    return send_from_directory(os.path.dirname(target_path), os.path.basename(target_path))

if __name__ == '__main__':
    # Security: Disable debug mode and restrict to localhost in production
    # Use SSH Tunneling (L 5000:localhost:5000) to access remotely
    app.run(host='127.0.0.1', port=5000, debug=False)
