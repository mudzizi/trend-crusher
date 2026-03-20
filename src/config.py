import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

"""
[Verified Best Optimization Results]
-----------------------------------------------------------------------------------
SYMBOL      | Vol_Mult | Trail_Mult | Risk_Pct | EMA_Period | Result     | MDD (%)
-----------------------------------------------------------------------------------
TRUMP/USDT  | 2.5      | 4.5        | 0.02     | 100        | +159.36%   | 16.80%
ETH/USDT    | 2.0      | 4.5        | 0.02     | 200        | +102.73%   | 18.02%
-----------------------------------------------------------------------------------
"""

# --- System Version ---
VERSION = "6.2.0"

CONFIG = {
    "VERSION": VERSION,
    # --- API KEYS (보안을 위해 .env에서 로드) ---
    "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY", ""),
    "BINANCE_SECRET": os.getenv("BINANCE_SECRET", ""),
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    
    # --- Operational Settings ---
    "DRY_RUN": os.getenv("DRY_RUN", "True").lower() == "true",            
    "SYMBOL": os.getenv("SYMBOL", "TRUMP/USDT"),     
    "SYMBOLS_LIST": ["TRUMP/USDT", "ETH/USDT", "XAU/USDT", "SOL/USDT"], # Multi-symbol list
    "MAX_CONCURRENT_TRADES": 3,                             # Limit total risk exposure
    "SYMBOL_WEIGHTS": {                                     # Allocation weight per symbol
        "TRUMP/USDT": 0.4,
        "ETH/USDT": 0.25,
        "XAU/USDT": 0.25,
        "SOL/USDT": 0.1
    },
    "SEED": float(os.getenv("SEED", 10000.0)),              
    "SIGNAL_TIMEFRAME": "1h",
    "TREND_TIMEFRAME": "4h",
    "CHECK_TIMEFRAME": "1m",
    "BACKTEST_DAYS": 365,       
    "LOOP_INTERVAL": 10,        
    "MAX_LEVERAGE": 5,          
    
    # --- Strategy Parameters (Default: TRUMP Best) ---
    "VOL_MULTIPLIER": 2.5,      
    "TRAILING_ATR_MULT": 4.5,   
    "RISK_PER_TRADE": 0.02,     
    "EMA_TREND_PERIOD": 100,
    
    # --- Fixed Indicators Setting ---
    "DONCHIAN_PERIOD": 20,
    "ATR_PERIOD": 14,
    "AVG_VOL_PERIOD": 20,
    "INITIAL_SL_ATR": 2.0,
    
    # --- Trading Costs ---
    "LOOP_INTERVAL": 10,        
    "MAX_LEVERAGE": 5,          
    "MARGIN_MODE": "ISOLATED",  # Target margin mode

    # --- Strategy Parameters (Default: TRUMP Best) ---
    "VOL_MULTIPLIER": 2.5,      
    "TRAILING_ATR_MULT": 4.5,   
    "RISK_PER_TRADE": 0.02,     
    "EMA_TREND_PERIOD": 100,
    # --- Symbol Specific Optimized Parameters ---
    "SYMBOL_SETTINGS": {
        "TRUMP/USDT": {
            "ALLOCATED_SEED": 4000.0,
            "VOL_MULTIPLIER": 2.5,
            "TRAILING_ATR_MULT": 4.5,
            "EMA_TREND_PERIOD": 100,
            "RISK_PER_TRADE": 0.02,
            "ADX_FILTER_LEVEL": 15
        },
        "ETH/USDT": {
            "ALLOCATED_SEED": 2500.0,
            "VOL_MULTIPLIER": 2.0,
            "TRAILING_ATR_MULT": 4.5,
            "EMA_TREND_PERIOD": 200,
            "RISK_PER_TRADE": 0.02,
            "ADX_FILTER_LEVEL": 15
        },
        "XAU/USDT": {
            "ALLOCATED_SEED": 2500.0,
            "VOL_MULTIPLIER": 2.5,
            "TRAILING_ATR_MULT": 4.5,
            "EMA_TREND_PERIOD": 200,
            "RISK_PER_TRADE": 0.02,
            "ADX_FILTER_LEVEL": 25
        },
        "SOL/USDT": {
            "ALLOCATED_SEED": 1000.0,
            "VOL_MULTIPLIER": 1.5,
            "TRAILING_ATR_MULT": 4.0,
            "EMA_TREND_PERIOD": 200,
            "RISK_PER_TRADE": 0.02,
            "ADX_FILTER_LEVEL": 15
        }
    },

    
    # --- New Strategy Improvements ---
    "ADX_FILTER_LEVEL": 15, 
    "USE_ADAPTIVE_TRAIL": True,
    "ADAPTIVE_TRAIL_STEPS": [
        {"pnl_pct": 10, "atr_mult": 3.5},
        {"pnl_pct": 20, "atr_mult": 2.5}
    ],
}
