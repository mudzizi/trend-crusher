import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

"""
Symbol-specific tuned defaults live in src/symbol_defaults.py.
The base CONFIG below is the default TRUMP/USDT operating profile.
"""

CONFIG = {
    # --- API KEYS (보안을 위해 .env에서 로드) ---
    "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY", ""),
    "BINANCE_SECRET": os.getenv("BINANCE_SECRET", ""),
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    
    # --- Operational Settings ---
    "DRY_RUN": os.getenv("DRY_RUN", "True").lower() == "true",            
    "SYMBOL": os.getenv("SYMBOL", "TRUMP/USDT"),     
    "SEED": float(os.getenv("SEED", 10000.0)),              
    "SIGNAL_TIMEFRAME": "1h",
    "TREND_TIMEFRAME": "2h",
    "CHECK_TIMEFRAME": "1m",
    "BACKTEST_DAYS": 365,       
    "LOOP_INTERVAL": 10,        
    "MAX_LEVERAGE": 5,          
    
    # --- Strategy Parameters (Default: TRUMP Best) ---
    "VOL_MULTIPLIER": 2.5,      
    "TRAILING_ATR_MULT": 4.5,   
    "RISK_PER_TRADE": 0.02,     
    "ENTRY_SPLIT_COUNT": 1,
    "EMA_TREND_PERIOD": 150,
    
    # --- Fixed Indicators Setting ---
    "DONCHIAN_PERIOD": 20,
    "ATR_PERIOD": 14,
    "AVG_VOL_PERIOD": 20,
    "INITIAL_SL_ATR": 2.0,
    
    # --- Trading Costs ---
    "FEE_RATE": 0.0004,
    "SLIPPAGE": 0.0005,
    "MAX_TRADE_LOSS_PCT_CAP": 2.0,
    "DATA_DIR": "data",
    "TIMESERIES_DIR": os.getenv("TIMESERIES_DIR", "timeseries"),
    "SNAPSHOT_DIR": os.getenv("SNAPSHOT_DIR", "artifacts/research/snapshots"),
    "ROLLING_TIMESERIES": os.getenv("ROLLING_TIMESERIES", "True").lower() == "true",
}
