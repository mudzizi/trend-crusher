import time
import os
import sys
import logging

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.config import CONFIG
from src.telegram_utils import TelegramNotifier

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger("CommandValidator")

def main():
    notifier = TelegramNotifier()
    
    if not notifier.enabled:
        logger.error("❌ Telegram Token or Chat ID not found in .env!")
        return

    logger.info("="*50)
    logger.info("📱 Telegram Command Interactive Validator")
    logger.info(f"Target Chat ID: {CONFIG['TELEGRAM_CHAT_ID']}")
    logger.info("Status: Waiting for commands from your phone...")
    logger.info("Commands to test: /status, /optimize, /apply, /stop, /close_all")
    logger.info("="*50)

    offset = None
    while True:
        try:
            updates = notifier.get_updates(offset)
            if updates and updates.get("ok"):
                for result in updates.get("result", []):
                    offset = result["update_id"] + 1
                    message = result.get("message", {})
                    text = message.get("text", "")
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    username = message.get("from", {}).get("username", "Unknown")
                    
                    logger.info(f"📩 Received: '{text}' from @{username} (ID: {chat_id})")
                    
                    # 1. Authorization Check
                    if chat_id != str(CONFIG["TELEGRAM_CHAT_ID"]):
                        logger.warning(f"🚫 Unauthorized Access Attempt! Chat ID {chat_id} is not {CONFIG['TELEGRAM_CHAT_ID']}")
                        notifier.send_message(f"⚠️ Access Denied. Your ID ({chat_id}) is not authorized.")
                        continue
                    
                    # 2. Command Interpretation
                    cmd_parts = text.split()
                    if not cmd_parts: continue
                    cmd = cmd_parts[0].lower()
                    
                    if cmd == "/status":
                        logger.info("✅ Interpreted as: GET_PORTFOLIO_STATUS")
                        notifier.notify_status("Test Success: Status command received and authorized.")
                    elif cmd == "/optimize":
                        sym = cmd_parts[1] if len(cmd_parts) > 1 else "ALL"
                        logger.info(f"✅ Interpreted as: RUN_OPTIMIZER for {sym}")
                        notifier.notify_status(f"Test Success: Optimization request for {sym} received.")
                    elif cmd == "/apply":
                        sym = cmd_parts[1] if len(cmd_parts) > 1 else "NONE"
                        logger.info(f"✅ Interpreted as: APPLY_PENDING_SETTINGS for {sym}")
                        notifier.notify_status(f"Test Success: Apply command for {sym} received.")
                    elif cmd == "/close_all":
                        logger.warning("🚨 Interpreted as: EMERGENCY_KILL_SWITCH")
                        notifier.notify_status("Test Success: EMERGENCY KILL SWITCH detected!")
                    else:
                        logger.info(f"❓ Unknown Command: {cmd}")
                        notifier.send_message(f"Unknown command '{cmd}'. Available: /status, /optimize, /apply, /stop, /close_all")

        except KeyboardInterrupt:
            logger.info("\nValidator stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
        
        time.sleep(2)

if __name__ == "__main__":
    main()
