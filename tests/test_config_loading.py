import os
import pytest
from src.config import load_config

def test_config_loading_fallback():
    # config.yaml이 없는 환경에서도 로딩이 되어야 함
    config = load_config()
    assert "VERSION" in config
    assert config["VERSION"] == "11.9.0"
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

if __name__ == "__main__":
    pytest.main([__file__])
