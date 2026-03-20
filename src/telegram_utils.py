import requests
import logging
from src.config import CONFIG

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = CONFIG["TELEGRAM_TOKEN"]
        self.chat_id = str(CONFIG["TELEGRAM_CHAT_ID"]) # Ensure string for comparison
        self.enabled = all([self.token, self.chat_id])
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send_message(self, text):
        if not self.enabled:
            logger.warning(f"[Telegram Disabled] {text}")
            return
        
        # Add [TEST] tag for DRY_RUN
        if CONFIG.get("DRY_RUN", True):
            text = f"🧪 *[TEST]*\n{text}"
        
        url = f"{self.base_url}/sendMessage"
        params = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            requests.get(url, params=params, timeout=10)
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    def get_updates(self, offset=None):
        """Polls for new messages from Telegram."""
        if not self.enabled: return None
        
        url = f"{self.base_url}/getUpdates"
        params = {"timeout": 10, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset
            
        try:
            response = requests.get(url, params=params, timeout=15)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch Telegram updates: {e}")
            return None

    def send_report(self, title, items):
        """Sends a structured report with a title and bullet points."""
        msg = f"📋 *{title}*\n\n"
        for key, val in items.items():
            msg += f"• *{key}*: {val}\n"
        self.send_message(msg)

    def notify_entry(self, side, price, sl, strength=None):
        msg = (
            f"🚀 *[ENTRY] {side}*\n"
            f"💰 Price: {price:,.2f}\n"
            f"🛡️ StopLoss: {sl:,.2f}\n"
            f"📊 Strength: {strength if strength else 'N/A'}\n"
            f"🤖 Mode: {'DRY RUN' if CONFIG['DRY_RUN'] else 'LIVE'}"
        )
        self.send_message(msg)

    def notify_exit(self, type, price, pnl_pct, pnl_usdt):
        icon = "✅" if pnl_pct > 0 else "❌"
        msg = (
            f"{icon} *[EXIT] {type}*\n"
            f"💰 Price: {price:,.2f}\n"
            f"📈 PnL: {pnl_pct:+.2f}%\n"
            f"💵 Profit: {pnl_usdt:+.2f} USDT"
        )
        self.send_message(msg)

    def notify_status(self, text):
        self.send_message(f"ℹ️ *[STATUS]* {text}")

    def notify_error(self, text):
        self.send_message(f"⚠️ *[ERROR]* {text}")
