import os
import pytest
from src.config import load_config

def test_config_loading_fallback():
    # config.yaml이 없는 환경에서도 로딩이 되어야 함
    config = load_config()
    from src.config import VERSION
    assert "VERSION" in config
    assert config["VERSION"] == VERSION
    assert "BINANCE_API_KEY" in config

def test_config_env_override(monkeypatch):
    # 환경 변수가 YAML 설정을 덮어씌우는지 확인
    monkeypatch.setenv("BINANCE_API_KEY", "TEST_KEY_FROM_ENV")
    monkeypatch.setenv("SEED", "99999.0")
    monkeypatch.setenv("DRY_RUN", "False")
    
    config = load_config()
    assert config["BINANCE_API_KEY"] == "TEST_KEY_FROM_ENV"
    assert config["SEED"] == 99999.0
    assert config["DRY_RUN"] is False

def test_xrp_trump_config_overrides():
    config = load_config()
    assert "SYMBOL_SETTINGS" in config
    settings = config["SYMBOL_SETTINGS"]
    
    # XRP Assertions
    assert "XRP/USDT" in settings
    xrp = settings["XRP/USDT"]
    assert xrp["USE_SNIPER"] is True
    assert xrp["USE_RETEST_MAKER"] is False
    assert xrp["RISK_PER_TRADE"] == 0.08
    assert xrp["VOL_MULTIPLIER"] == 2.2
    assert xrp["TRAILING_ATR_MULT"] == 3.0
    assert xrp["ADX_FILTER_LEVEL"] == 18
    assert xrp["DONCHIAN_PERIOD"] == 20
    assert xrp["USE_ADAPTIVE_TRAIL"] is False
    assert xrp["INITIAL_SL_ATR"] == 2.0
    assert xrp["BE_GUARD_THRESHOLD"] == 3.0
    assert xrp["CHAOS_THRESHOLD"] == 20.0
    assert xrp["EMA_TREND_PERIOD"] == 150

    # TRUMP Assertions
    assert "TRUMP/USDT" in settings
    trump = settings["TRUMP/USDT"]
    assert trump["USE_SNIPER"] is False
    assert trump["USE_RETEST_MAKER"] is False
    assert trump["RISK_PER_TRADE"] == 0.10
    assert trump["VOL_MULTIPLIER"] == 1.3
    assert trump["TRAILING_ATR_MULT"] == 5.0
    assert trump["ADX_FILTER_LEVEL"] == 35
    assert trump["DONCHIAN_PERIOD"] == 20
    assert trump["USE_ADAPTIVE_TRAIL"] is True
    assert trump["INITIAL_SL_ATR"] == 2.0
    assert trump["BE_GUARD_THRESHOLD"] == 1.5
    assert trump["CHAOS_THRESHOLD"] == 10.0
    assert trump["EMA_TREND_PERIOD"] == 150

    # SUI Assertions
    assert "SUI/USDT" in settings
    sui = settings["SUI/USDT"]
    assert sui["USE_SNIPER"] is False
    assert sui["USE_RETEST_MAKER"] is False
    assert sui["RISK_PER_TRADE"] == 0.10
    assert sui["VOL_MULTIPLIER"] == 3.0
    assert sui["TRAILING_ATR_MULT"] == 5.0
    assert sui["ADX_FILTER_LEVEL"] == 35
    assert sui["DONCHIAN_PERIOD"] == 20
    assert sui["USE_ADAPTIVE_TRAIL"] is False
    assert sui["INITIAL_SL_ATR"] == 1.5
    assert sui["BE_GUARD_THRESHOLD"] == 3.0
    assert sui["CHAOS_THRESHOLD"] == 20.0
    assert sui["EMA_TREND_PERIOD"] == 25

if __name__ == "__main__":
    pytest.main([__file__])
