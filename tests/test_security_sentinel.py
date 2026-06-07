import unittest
import os
import sqlite3
from src.db_manager import DBManager
from src.security import SecuritySentinel
from flask import Flask

class TestSecuritySentinel(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_security.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = DBManager(db_path=self.db_path)
        self.security = SecuritySentinel(self.db)
        
        # Mock Flask App Context
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_whitelist_validation(self):
        self.assertTrue(self.security.is_whitelisted("/"))
        self.assertTrue(self.security.is_whitelisted("/static/style.css"))
        self.assertTrue(self.security.is_whitelisted("/reports/backtest.png"))
        self.assertTrue(self.security.is_whitelisted("/favicon.ico"))
        
        self.assertFalse(self.security.is_whitelisted("/.env"))
        self.assertFalse(self.security.is_whitelisted("/google-service-account.json"))
        self.assertFalse(self.security.is_whitelisted("/admin"))

    def test_ip_blocking_logic(self):
        ip = "1.2.3.4"
        self.assertFalse(self.db.is_ip_blocked(ip))
        
        # Block for 24h
        self.db.block_ip(ip, "Test block")
        self.assertTrue(self.db.is_ip_blocked(ip))

    def test_expiration_logic(self):
        ip = "5.6.7.8"
        # Block for -1 hours (guaranteed expire)
        self.db.block_ip(ip, "Expired block", duration_hours=-1)
        
        # is_ip_blocked should cleanup and return False
        self.assertFalse(self.db.is_ip_blocked(ip))

if __name__ == "__main__":
    unittest.main()
