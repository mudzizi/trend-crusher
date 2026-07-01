from flask import Flask, render_template, send_from_directory, request, abort, g, redirect, url_for, make_response
from src.db_manager import DBManager
from src.security import SecuritySentinel
from src.visualizer import TradingVisualizer
from src.config import CONFIG
from src.indicators import calculate_donchian, calculate_ema, calculate_avg_vol, calculate_adx
import os
import pandas as pd
import ccxt
import traceback
import time
import logging
import threading
from datetime import datetime

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
security = SecuritySentinel(db)

def log_security_stats():
    """Periodically logs the number of blocked IPs."""
    while True:
        try:
            count = db.get_blocked_ip_count()
            if count > 0:
                logger.info(f"SECURITY STATUS: {count} IPs currently blocked (24h Whitelist Defense)")
        except Exception as e:
            logger.error(f"Error logging security stats: {e}")
        time.sleep(3600) # Log every hour

# Start periodic logging thread
threading.Thread(target=log_security_stats, daemon=True).start()

viz = TradingVisualizer()
exchange = ccxt.binance({
    'options': {'defaultType': 'future'},
    'timeout': 10000
})

@app.before_request
def secure_access():
    return security.check_request()

@app.route('/')
def index():
    # Use scripts.dashboard.exchange, but instantiate local client if not a mock to ensure thread-safety
    local_exchange = exchange
    if not (type(exchange).__name__ in ('MagicMock', 'Mock', 'AsyncMock')):
        local_exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'timeout': 10000
        })
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
                ticker = local_exchange.fetch_ticker(sym)
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
                
                # Filter: Only show symbols present in current CONFIG
                if sym not in symbols:
                    continue
                    
                sym_settings = CONFIG.get("SYMBOL_SETTINGS", {}).get(sym, {})
                vol_mult = sym_settings.get("VOL_MULTIPLIER", CONFIG.get("VOL_MULTIPLIER", 2.2))
                
                # Fetch hourly history for charting (last 48h)
                hist_df = db.get_history_1h(sym, limit=48)
                if not hist_df.empty:
                    # Convert UTC to KST
                    hist_df['timestamp'] = pd.to_datetime(hist_df['timestamp']) + pd.Timedelta(hours=9)
                
                prices = hist_df['close'].tolist()
                ema_values = hist_df['ema'].tolist()
                upper_bands = hist_df['donchian_upper'].tolist()
                lower_bands = hist_df['donchian_lower'].tolist()
                volumes = hist_df['volume'].tolist()
                adx_values = hist_df['adx'].tolist()
                chaos_values = hist_df['chaos'].tolist() if 'chaos' in hist_df.columns else [0]*len(prices)
                chop_values = hist_df['chop'].tolist() if 'chop' in hist_df.columns else [0]*len(prices)
                adx_4h_values = hist_df['adx_4h'].tolist() if 'adx_4h' in hist_df.columns else [0]*len(prices)
                labels = [t.strftime('%m/%d %H:%M') for t in hist_df['timestamp']] if not hist_df.empty else []

                # Add the very latest live data point
                prices.append(row['last_price'])
                
                ema_val = row.get('ema_value') or (ema_values[-1] if ema_values else row['last_price'])
                ema_values.append(ema_val)
                
                upper_bands.append(row['upper_band'])
                lower_bands.append(row['lower_column'])
                
                # Compute actual volume multiplier relative to average volume
                cur_vol_ratio = row['vol_ratio']
                actual_vol_mult = (cur_vol_ratio / 100.0) * vol_mult
                avg_vol_20 = sum(volumes[-20:]) / len(volumes[-20:]) if volumes else 1.0
                volumes.append(actual_vol_mult * avg_vol_20)
                
                adx_values.append(row['adx_value'])
                chaos_values.append(row.get('chaos_value', 0))
                chop_values.append(row.get('chop_value', 0))
                adx_4h_values.append(row.get('adx_4h_value', 0))
                
                current_kst = datetime.now()
                labels.append(current_kst.strftime('%m/%d %H:%M') + " (Now)")

                # Fetch Bot State to check if ambushing
                state = db.get_bot_state(sym)
                is_ambushing = bool(state.get('sniper_order_id') or state.get('retest_order_id')) if state else False

                # Per-symbol thresholds for entry readiness checklist
                adx_limit = sym_settings.get("ADX_FILTER_LEVEL", CONFIG.get("ADX_FILTER_LEVEL", 20.0))
                adx_4h_limit = sym_settings.get("ADX_4H_THRESHOLD", CONFIG.get("ADX_4H_THRESHOLD", 15.0))
                chaos_limit = sym_settings.get("CHAOS_THRESHOLD", CONFIG.get("CHAOS_THRESHOLD", 20.0))
                
                # Compute entry readiness checklist
                cur_adx = row['adx_value']
                cur_adx_4h = row.get('adx_4h_value', 0)
                cur_chaos = row.get('chaos_value', 0)
                cur_chop = row.get('chop_value', 50)
                cur_slope = row.get('slope_value', 0)
                cur_squeeze = row.get('squeeze_value', 0)
                cur_price = row['last_price']
                cur_ema = ema_val
                cur_upper = row['upper_band']
                cur_lower = row['lower_column']
                
                is_long = cur_price > cur_ema

                # Parameter Normalization (Hysteresis)
                v_target = vol_mult * 0.8 if is_ambushing else vol_mult
                a_target = adx_limit * 0.8 if is_ambushing else adx_limit
                a4_target = adx_4h_limit * 0.8 if is_ambushing else adx_4h_limit

                # Dynamic Barrier (applied if chaos_limit > 0)
                v_mult_final = v_target
                a_target_final = a_target
                a4_target_final = a4_target
                
                if chaos_limit > 0:
                    # Choppiness Scaling
                    if cur_chop > 61.8:
                        v_mult_final *= 1.8
                    elif cur_chop < 38.2:
                        v_mult_final *= 0.8
                    # Squeeze scaling
                    if cur_squeeze > 0:
                        v_mult_final *= 0.7
                    # Short position bias
                    if not is_long:
                        v_mult_final *= 0.6
                        a_target_final *= 0.7
                        a4_target_final *= 0.7

                # Checks
                chaos_ok = cur_chaos >= chaos_limit if chaos_limit > 0 else True
                slope_ok = (cur_slope > 0 and is_long) or (cur_slope < 0 and not is_long) if chaos_limit > 0 else True
                chop_ok = cur_chop < 61.8
                adx_ok = cur_adx >= a_target_final
                adx_4h_ok = cur_adx_4h >= a4_target_final
                vol_ok = actual_vol_mult >= v_mult_final
                
                # Position overlay data
                pos_data = None
                for pos in active_positions:
                    if pos['symbol'] == sym:
                        pos_data = pos
                        break

                live_monitors.append({
                    "symbol": sym,
                    "vol_ratio": round(actual_vol_mult, 2),
                    "adx_value": round(row['adx_value'], 1),
                    "adx_4h_value": round(cur_adx_4h, 1),
                    "chaos_value": round(cur_chaos, 1),
                    "chop_value": round(cur_chop, 1),
                    "squeeze": "YES" if cur_squeeze > 0 else "NO",
                    "slope": round(cur_slope, 4),
                    "trend_ok": bool(row['trend_ok']),
                    "score": round(row['signal_score'], 1),
                    "price": cur_price,
                    "upper": cur_upper,
                    "lower": cur_lower,
                    "mode": "Sniper" if sym_settings.get("USE_SNIPER", CONFIG.get("USE_SNIPER")) else ("Retest" if sym_settings.get("USE_RETEST_MAKER", CONFIG.get("USE_RETEST_MAKER")) else "Market"),
                    "vol_mult": round(v_mult_final, 2),
                    "adx_limit": round(a_target_final, 1),
                    "adx_4h_limit": round(a4_target_final, 1),
                    "chaos_limit": chaos_limit,
                    "direction": "LONG" if is_long else "SHORT",
                    # Entry Readiness Checklist
                    "ready_chaos": chaos_ok,
                    "ready_slope": slope_ok,
                    "ready_chop": chop_ok,
                    "ready_adx": adx_ok,
                    "ready_adx_4h": adx_4h_ok,
                    "ready_vol": vol_ok,
                    "ready_squeeze": cur_squeeze > 0,
                    # Position overlay
                    "position": pos_data,
                    "history": {
                        "prices": prices,
                        "ema": ema_values,
                        "upper": upper_bands,
                        "lower": lower_bands,
                        "volume": volumes,
                        "adx": adx_values,
                        "adx_4h": adx_4h_values,
                        "chaos": chaos_values,
                        "chop": chop_values,
                        "labels": labels
                    }
                })
        except Exception as e:
            logger.error(f"Error fetching live status history: {e}")

        # --- [NEW] Sort monitors by symbol to keep consistent order ---
        live_monitors = sorted(live_monitors, key=lambda x: x['symbol'])

        # 3. Fetch Market Summary
        for sym in symbols:
            try:
                ticker = local_exchange.fetch_ticker(sym)
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
    if not equity_df.empty:
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp']) + pd.Timedelta(hours=9)
        
    chart_data = {
        "labels": [t.strftime('%m-%d %H:%M') for t in equity_df['timestamp']] if not equity_df.empty else [],
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

@app.route('/static/<path:filename>')
def serve_static(filename):
    # Security: Normalize path and prevent Path Traversal
    target_path = os.path.abspath(os.path.join(static_dir, filename))
    base_path = os.path.abspath(static_dir)
    
    if not target_path.startswith(base_path):
        return "Access Denied: Invalid Path", 403
        
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    error_msg = None
    is_secure = request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
    if request.method == 'POST':
        password = request.form.get('password')
        hashed_pw = CONFIG.get("DASHBOARD_PASSWORD_HASH")
        if not hashed_pw:
            token = security.generate_token()
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('access_token', token, max_age=7*24*3600, httponly=True, secure=is_secure, samesite='Lax')
            return resp
            
        from werkzeug.security import check_password_hash
        if check_password_hash(hashed_pw, password):
            token = security.generate_token()
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('access_token', token, max_age=7*24*3600, httponly=True, secure=is_secure, samesite='Lax')
            return resp
        else:
            error_msg = "Invalid password. Please try again."
            
    # GET: If already logged in, redirect to index
    token = request.cookies.get('access_token')
    is_valid, _ = security.check_token(token)
    if is_valid:
        return redirect(url_for('index'))
        
    return render_template('login.html', error=error_msg, version=CONFIG.get("VERSION", "N/A"))

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    is_secure = request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
    # Clear the cookie
    resp.set_cookie('access_token', '', max_age=0, httponly=True, secure=is_secure, samesite='Lax')
    return resp

@app.after_request
def set_renewed_token(response):
    if hasattr(g, 'new_token') and g.new_token:
        is_secure = request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
        response.set_cookie(
            'access_token',
            g.new_token,
            max_age=7 * 24 * 3600,
            httponly=True,
            secure=is_secure,
            samesite='Lax'
        )
    return response

from waitress import serve

if __name__ == '__main__':
    cert_path = os.path.join(project_root, 'certs', 'fullchain.pem')
    key_path = os.path.join(project_root, 'certs', 'privkey.pem')
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        logger.info("Starting TrendCrusher Dashboard with Flask Server (HTTPS Enabled)")
        app.run(host='0.0.0.0', port=5000, ssl_context=(cert_path, key_path))
    else:
        # Security: Use Waitress for production-grade serving with low memory overhead
        # Bind to 127.0.0.1 for maximum security (access via SSH Tunneling)
        logger.info("Starting TrendCrusher Dashboard with Waitress (Production)")
        logger.info("Access locally via SSH Tunnel: ssh -L 5000:localhost:5000 user@gcp-ip")
        serve(app, host='127.0.0.1', port=5000, threads=4)
