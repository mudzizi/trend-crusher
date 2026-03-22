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

    def set_commands(self):
        """Registers the command menu in the Telegram app for easy clicking."""
        if not self.enabled: return
        
        commands = [
            {"command": "status", "description": "📊 Portfolio Status & PnL"},
            {"command": "sniper_on", "description": "🏹 Enable Sniper Ambush"},
            {"command": "sniper_off", "description": "🚫 Disable Sniper Ambush"},
            {"command": "stop", "description": "🛑 Stop Entry Logic"},
            {"command": "resume", "description": "▶️ Resume Entry Logic"},
            {"command": "close_all", "description": "🆘 EMERGENCY: Close All & Stop"}
        ]
        
        url = f"{self.base_url}/setMyCommands"
        try:
            r = requests.post(url, json={"commands": commands}, timeout=10)
            if r.status_code == 200:
                logger.info("✅ Telegram Bot Commands Menu Registered Successfully.")
            else:
                logger.warning(f"⚠️ Failed to register Bot Commands Menu: {r.text}")
        except Exception as e:
            logger.error(f"Error setting bot commands: {e}")

    def send_message(self, text, reply_markup=None):
        if not self.enabled:
            logger.warning(f"[Telegram Disabled] {text}")
            return
        
        # Add [TEST] tag for DRY_RUN
        is_dry = CONFIG.get("DRY_RUN", True)
        if is_dry:
            text = f"🧪 *[TEST]*\n{text}"
        
        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": self.chat_id, 
            "text": text, 
            "parse_mode": "Markdown",
        }
        if reply_markup:
            params["reply_markup"] = reply_markup
            
        try:
            requests.post(url, json=params, timeout=10)
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
        leverage = CONFIG.get("MAX_LEVERAGE", 1)
        roe = pnl_pct * leverage
        
        msg = (
            f"{icon} *[EXIT] {type}*\n"
            f"💰 Price: {price:,.2f}\n"
            f"📈 Asset PnL: {pnl_pct:+.2f}%\n"
            f"🔥 ROE ({leverage}x): {roe:+.2f}%\n"
            f"💵 Profit: {pnl_usdt:+.2f} USDT"
        )
        self.send_message(msg)

    def notify_status(self, text):
        self.send_message(f"ℹ️ *[STATUS]* {text}")

    def notify_error(self, text):
        self.send_message(f"⚠️ *[ERROR]* {text}")
