import pytest
import os
import sqlite3
from src.sentinel import MarketSentinel
from src.db_manager import DBManager
from src.security import SecuritySentinel
from flask import Flask

@pytest.fixture
def sentinel_config():
    return {
        "SENTINEL_DAILY_LOSS_LIMIT": -5.0,
        "SENTINEL_CHOP_THRESHOLD": 70.0
    }

def test_sentinel_kill_switch(sentinel_config):
    sentinel = MarketSentinel(config=sentinel_config)
    
    # Not killed initially
    assert sentinel.is_killed is False
    
    # Safe loss (-3%)
    assert sentinel.check_kill_switch(-3.0) is False
    assert sentinel.is_killed is False
    
    # Limit hit (-6%)
    assert sentinel.check_kill_switch(-6.0) is True
    assert sentinel.is_killed is True
    assert "Daily Loss Limit Reached" in sentinel.kill_reason
    
    # Reset
    sentinel.reset_kill_switch()
    assert sentinel.is_killed is False

def test_sentinel_is_market_safe(sentinel_config):
    sentinel = MarketSentinel(config=sentinel_config)
    
    # Safe condition
    row_safe = {'chop': 50.0}
    safe, reason = sentinel.is_market_safe(row_safe)
    assert safe is True
    assert reason == "SAFE"
    
    # Unsafe condition (high chop)
    row_unsafe = {'chop': 75.0}
    safe, reason = sentinel.is_market_safe(row_unsafe)
    assert safe is False
    assert "SIDEWAYS_CHOP" in reason
    
    # Killed condition
    sentinel.is_killed = True
    sentinel.kill_reason = "Manual kill"
    safe, reason = sentinel.is_market_safe(row_safe)
    assert safe is False
    assert "KILL_SWITCH_ACTIVE" in reason

# --- From test_security_sentinel.py ---
@pytest.fixture
def temp_db_path():
    db_path = "test_security.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)

def test_whitelist_validation(temp_db_path):
    db = DBManager(db_path=temp_db_path)
    security = SecuritySentinel(db)
    
    assert security.is_whitelisted("/")
    assert security.is_whitelisted("/static/style.css")
    assert security.is_whitelisted("/reports/backtest.png")
    assert security.is_whitelisted("/favicon.ico")
    
    assert not security.is_whitelisted("/.env")
    assert not security.is_whitelisted("/google-service-account.json")
    assert not security.is_whitelisted("/admin")

def test_ip_blocking_logic(temp_db_path):
    db = DBManager(db_path=temp_db_path)
    security = SecuritySentinel(db)
    ip = "1.2.3.4"
    assert not db.is_ip_blocked(ip)
    
    # Block for 24h
    db.block_ip(ip, "Test block")
    assert db.is_ip_blocked(ip)

def test_expiration_logic(temp_db_path):
    db = DBManager(db_path=temp_db_path)
    security = SecuritySentinel(db)
    ip = "5.6.7.8"
    # Block for -1 hours (guaranteed expire)
    db.block_ip(ip, "Expired block", duration_hours=-1)
    
    # is_ip_blocked should cleanup and return False
    assert not db.is_ip_blocked(ip)
