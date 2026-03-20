from src.config import CONFIG
from src.symbol_defaults import apply_symbol_defaults


def test_apply_symbol_defaults_for_btc():
    resolved = apply_symbol_defaults(CONFIG, "btc/usdt")

    assert resolved["SYMBOL"] == "BTC/USDT"
    assert resolved["TREND_TIMEFRAME"] == "2h"
    assert resolved["EMA_TREND_PERIOD"] == 100
    assert resolved["ENTRY_SPLIT_COUNT"] == 1
    assert resolved["RISK_PER_TRADE"] == 0.01
    assert resolved["MAX_TRADE_LOSS_PCT_CAP"] == 1.0


def test_apply_symbol_defaults_for_eth():
    resolved = apply_symbol_defaults(CONFIG, "ETH/USDT")

    assert resolved["SYMBOL"] == "ETH/USDT"
    assert resolved["TREND_TIMEFRAME"] == "4h"
    assert resolved["EMA_TREND_PERIOD"] == 200
    assert resolved["ENTRY_SPLIT_COUNT"] == 2
    assert resolved["RISK_PER_TRADE"] == 0.02


def test_apply_symbol_defaults_keeps_unknown_symbol_values():
    resolved = apply_symbol_defaults(CONFIG, "SOL/USDT")

    assert resolved["SYMBOL"] == "SOL/USDT"
    assert resolved["TREND_TIMEFRAME"] == CONFIG["TREND_TIMEFRAME"]
    assert resolved["EMA_TREND_PERIOD"] == CONFIG["EMA_TREND_PERIOD"]
