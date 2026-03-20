from __future__ import annotations

from copy import deepcopy


SYMBOL_DEFAULTS = {
    "TRUMP/USDT": {
        "VOL_MULTIPLIER": 2.5,
        "TRAILING_ATR_MULT": 4.5,
        "RISK_PER_TRADE": 0.02,
        "ENTRY_SPLIT_COUNT": 1,
        "TREND_TIMEFRAME": "2h",
        "EMA_TREND_PERIOD": 150,
        "MAX_TRADE_LOSS_PCT_CAP": 2.0,
    },
    "ETH/USDT": {
        "VOL_MULTIPLIER": 2.0,
        "TRAILING_ATR_MULT": 4.5,
        "RISK_PER_TRADE": 0.02,
        "ENTRY_SPLIT_COUNT": 2,
        "TREND_TIMEFRAME": "4h",
        "EMA_TREND_PERIOD": 200,
        "MAX_TRADE_LOSS_PCT_CAP": 2.0,
    },
    "BTC/USDT": {
        "VOL_MULTIPLIER": 2.0,
        "TRAILING_ATR_MULT": 4.5,
        "RISK_PER_TRADE": 0.01,
        "ENTRY_SPLIT_COUNT": 1,
        "TREND_TIMEFRAME": "2h",
        "EMA_TREND_PERIOD": 100,
        "MAX_TRADE_LOSS_PCT_CAP": 1.0,
    },
}


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def apply_symbol_defaults(config: dict, symbol: str) -> dict:
    resolved = deepcopy(config)
    resolved_symbol = normalize_symbol(symbol)
    resolved["SYMBOL"] = resolved_symbol
    defaults = SYMBOL_DEFAULTS.get(resolved_symbol)
    if defaults:
        resolved.update(defaults)
    return resolved
