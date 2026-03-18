import requests
from src.config import CONFIG

class TelegramNotifier:
    def __init__(self):
        self.token = CONFIG["TELEGRAM_TOKEN"]
        self.chat_id = CONFIG["TELEGRAM_CHAT_ID"]
        self.enabled = all([self.token, self.chat_id])

    def send_message(self, text):
        if not self.enabled:
            print(f"[Telegram Disabled] {text}")
            return
        
        # DRY_RUN 모드일 경우 상단에 [TEST] 태그 추가
        if CONFIG.get("DRY_RUN", True):
            text = f"🧪 *[TEST]*\n{text}"
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        params = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            requests.get(url, params=params, timeout=5)
        except Exception as e:
            print(f"Telegram error: {e}")

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
