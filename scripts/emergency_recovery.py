import sqlite3
from datetime import datetime
import os

def recover_state(symbol="ETH/USDT"):
    db_path = "trades.db"
    if not os.path.exists(db_path):
        print(f"❌ Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"🔧 Starting recovery for {symbol}...")

    # 1. Fetch current entry price if possible to calculate dummy PnL
    cursor.execute("SELECT open_price, quantity FROM trades WHERE symbol = ? AND status = 'OPEN'", (symbol,))
    row = cursor.fetchone()
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if row:
        open_p, qty = row[0], row[1]
        print(f"Found open trade: {symbol} at {open_p}")
        # Close with 1.5% loss (Typical SL)
        close_p = open_p * 1.015 
        pnl_usdt = (open_p - close_p) * qty # Short position PnL
        
        cursor.execute("""
            UPDATE trades 
            SET status = 'CLOSED',
                close_time = ?,
                close_price = ?,
                pnl_pct = -1.5,
                pnl_usdt = ?
            WHERE symbol = ? AND status = 'OPEN'
        """, (now_str, close_p, pnl_usdt, symbol))
        print(f"Closed trade history for {symbol}")

    # 2. bot_state 초기화 (포지션 없음 상태로)
    cursor.execute("""
        UPDATE bot_state 
        SET position = 0, 
            entry_price = 0, 
            quantity = 0, 
            sl_order_id = NULL, 
            sniper_order_id = NULL, 
            retest_order_id = NULL,
            last_updated = ?
        WHERE symbol = ?
    """, (now_str, symbol))
    
    conn.commit()
    print(f"✅ Recovery complete! {symbol} state reset to IDLE.")
    conn.close()

if __name__ == "__main__":
    recover_state("ETH/USDT")
