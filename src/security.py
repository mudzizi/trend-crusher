import logging
import re
from datetime import datetime, timezone
from flask import request, abort, redirect, g
from itsdangerous import URLSafeTimedSerializer
from src.config import CONFIG

logger = logging.getLogger(__name__)

class SecuritySentinel:
    """
    Whitelist-based security engine with Hashed Auth and IP defense.
    """
    # Allowed path patterns (Regex) - Strict whitelist
    WHITELIST_PATTERNS = [
        r"^/$",                               # Root
        r"^/login$",                          # Login page & POST request
        r"^/logout$",                         # Logout
        r"^/static/[\w\-\./]+\.[a-z0-9]+$",   # Static files (with extension)
        r"^/reports/[\w\-\./]+\.[a-z0-9]+$",  # Report files (with extension)
        r"^/favicon\.ico$"                    # Browser icon
    ]

    def __init__(self, db_manager):
        self.db = db_manager
        self._compiled_whitelist = [re.compile(p) for p in self.WHITELIST_PATTERNS]
        # Store the hash from config
        self.password_hash = CONFIG.get("DASHBOARD_PASSWORD_HASH")
        # Use password hash as secret key for token signing to persist sessions across restarts
        secret_key = self.password_hash or "default_fallback_secret_key_12345"
        self.serializer = URLSafeTimedSerializer(secret_key)

    def generate_token(self):
        """Generates a signed access token."""
        return self.serializer.dumps({"authenticated": True})

    def check_token(self, token):
        """Verifies the access token. Returns (is_valid, should_renew)."""
        if not self.password_hash:
            return True, False # No password set, allow access
            
        if not token:
            return False, False
            
        try:
            # Token duration is 7 days
            max_age = 7 * 24 * 3600
            payload, timestamp = self.serializer.loads(token, max_age=max_age, return_timestamp=True)
            
            # Check if requested within 1 day (86400 seconds) of issuance to renew session
            now = datetime.now(timezone.utc)
            age = (now - timestamp).total_seconds()
            
            should_renew = (0 <= age <= 86400)
            return True, should_renew
        except Exception:
            return False, False

    def is_whitelisted(self, path):
        """Checks if the path is in the allowed whitelist and prevents traversal."""
        # 1. Path Traversal prevention
        if ".." in path:
            return False
            
        # 2. Check against strict whitelist patterns
        return any(pattern.match(path) for pattern in self._compiled_whitelist)

    def check_request(self):
        """
        Validates the current Flask request.
        To be used in @app.before_request
        """
        ip = request.remote_addr
        path = request.path

        # 1. Check if IP is already blocked (Exclude localhost from block check)
        if ip != "127.0.0.1" and self.db.is_ip_blocked(ip):
            logger.info(f"Blocked access attempt from {ip} to {path}")
            abort(403, description="Access Denied: Your IP is temporarily blocked.")

        # 2. Check if path is whitelisted
        if not self.is_whitelisted(path):
            # Relaxed blocking: Don't block localhost, just block others
            if ip != "127.0.0.1":
                self.db.block_ip(ip, f"Unauthorized path access: {path}", duration_hours=24)
                logger.warning(f"SECURITY ALERT: Blocked IP {ip} for 24h (Unauthorized path: {path})")
            else:
                logger.warning(f"SECURITY WARNING: Local access to unauthorized path: {path}")
            
            abort(403, description="Access Denied: Unauthorized request pattern.")

        # 3. Access Token Check (Only for root/main page or sensitive reports)
        if path == "/" or path.startswith("/reports/"):
            token = request.cookies.get('access_token')
            is_valid, should_renew = self.check_token(token)
            if not is_valid:
                return redirect('/login')
            if should_renew:
                g.new_token = self.generate_token()

        return None # Proceed to route handler
