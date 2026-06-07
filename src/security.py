import logging
import re
import base64
from flask import request, abort, Response
from werkzeug.security import check_password_hash
from src.config import CONFIG

logger = logging.getLogger(__name__)

class SecuritySentinel:
    """
    Whitelist-based security engine with Hashed Auth and IP defense.
    """
    # Allowed path patterns (Regex) - Strict whitelist
    WHITELIST_PATTERNS = [
        r"^/$",                               # Root
        r"^/static/[\w\-\./]+\.[a-z0-9]+$",   # Static files (with extension)
        r"^/reports/[\w\-\./]+\.[a-z0-9]+$",  # Report files (with extension)
        r"^/favicon\.ico$"                    # Browser icon
    ]

    def __init__(self, db_manager):
        self.db = db_manager
        self._compiled_whitelist = [re.compile(p) for p in self.WHITELIST_PATTERNS]
        # Store the hash from config
        self.password_hash = CONFIG.get("DASHBOARD_PASSWORD_HASH")

    def check_auth(self, auth):
        """Verifies Basic Auth credentials using hashing."""
        if not self.password_hash:
            return True # No password set, allow access
            
        if not auth or not auth.startswith('Basic '):
            return False
        
        try:
            encoded_credentials = auth.split(' ')[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            username, password = decoded_credentials.split(':')
            # Username is ignored, only password matters
            return check_password_hash(self.password_hash, password)
        except:
            return False

    def authenticate(self):
        """Sends a 401 response that enables basic auth."""
        return Response(
            'Could not verify your access level for that URL.\n'
            'You have to login with proper credentials', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'}
        )

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

        # 3. Hashed Auth Check (Only for root/main page or sensitive reports)
        if path == "/" or path.startswith("/reports/"):
            auth = request.headers.get('Authorization')
            if not self.check_auth(auth):
                return self.authenticate()

        return None # Proceed to route handler
