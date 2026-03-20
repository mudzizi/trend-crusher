import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

"""
[Verified Best Optimization Results - S-Tier]
-----------------------------------------------------------------------------------
SYMBOL      | Vol_Mult | Trail_Mult | Risk_Pct | EMA_Period | ADX_F | Result (1Y)
-----------------------------------------------------------------------------------
TRUMP/USDT  | 2.5      | 4.5        | 0.02     | 100        | 15    | +210.07%
XAU/USDT    | 2.5      | 4.5        | 0.02     | 200        | 25    | +186.89%
ETH/USDT    | 2.0      | 4.5        | 0.02     | 200        | 15    | +161.44%
-----------------------------------------------------------------------------------
"""

# --- System Version ---
VERSION = "11.0.0"

CONFIG = {
    "VERSION": VERSION,
    # --- API KEYS ---
    "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY", ""),
    "BINANCE_SECRET": os.getenv("BINANCE_SECRET", ""),
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
    
    # --- Operational Settings ---
    "DRY_RUN": os.getenv("DRY_RUN", "True").lower() == "true",            
    "SYMBOL": os.getenv("SYMBOL", "TRUMP/USDT"),     
    "SYMBOLS_LIST": ["TRUMP/USDT", "ETH/USDT", "XAU/USDT", "SOL/USDT"],
    "MAX_CONCURRENT_TRADES": 3,
    "MARGIN_MODE": "ISOLATED",
    "SEED": float(os.getenv("SEED", 10000.0)),              
    
    # --- Timeframes ---
    "SIGNAL_TIMEFRAME": "1h",
    "TREND_TIMEFRAME": "4h",
    "CHECK_TIMEFRAME": "1m",
    "LOOP_INTERVAL": 10,
    
    # --- Trading Costs ---
    "FEE_RATE": 0.0004,         # Standard Taker Fee
    "MAKER_FEE_RATE": 0.0002,   # Standard Maker Fee
    "SLIPPAGE": 0.0005,         # Default Slippage (0.05%)
    "DATA_DIR": "data",
    
    # --- Strategy Parameters (Global Defaults) ---
    "VOL_MULTIPLIER": 2.5,      
    "TRAILING_ATR_MULT": 4.5,   
    "RISK_PER_TRADE": 0.02,     
    "EMA_TREND_PERIOD": 100,
    "DONCHIAN_PERIOD": 20,
    "ATR_PERIOD": 14,
    "AVG_VOL_PERIOD": 20,
    "INITIAL_SL_ATR": 2.0,
    "ADX_FILTER_LEVEL": 15,
    "MAX_LEVERAGE": 5,

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

    # --- Strategy Improvements ---
    "USE_ADAPTIVE_TRAIL": True,
    "ADAPTIVE_TRAIL_STEPS": [
        {"pnl_pct": 10, "atr_mult": 3.5},
        {"pnl_pct": 20, "atr_mult": 2.5}
    ],
    
    # --- The Sniper (v11.0.0) ---
    "SNIPER_PROXIMITY_PCT": 0.005, 
}
