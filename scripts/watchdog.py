import subprocess
import time
import sys
import os
import logging

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from src.config import CONFIG
from src.telegram_utils import TelegramNotifier

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [Watchdog] %(message)s'
)
logger = logging.getLogger("Watchdog")

def run_bot():
    """Runs the main bot process and monitors it."""
    notifier = TelegramNotifier()
    cmd = [sys.executable, "scripts/live_bot_async.py"]
    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    while True:
        logger.info("🚀 Starting TrendCrusher Bot...")
        # Start the bot as a subprocess
        process = subprocess.Popen(cmd, env=env)
        
        # Wait for the process to finish
        exit_code = process.wait()
        
        if exit_code == 0:
            logger.info("✅ Bot stopped normally (Exit Code 0). Stopping Watchdog.")
            break
        else:
            logger.error(f"🚨 Bot CRASHED with Exit Code {exit_code}!")
            error_msg = f"🆘 *[WATCHDOG]* Bot died unexpectedly (Code: {exit_code})."
            if exit_code == -9: # SIGKILL / OOM Killer
                error_msg += "\n⚠️ Reason: OOM Killer (Memory Leak?) or Force Kill detected."
            
            notifier.notify_error(f"{error_msg}\n🔄 *Auto-restarting in 10s...*")
            
            time.sleep(10) # Pause before restart

if __name__ == "__main__":
    logger.info("🐕 Watchdog active. Monitoring TrendCrusher...")
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("👋 Watchdog stopped by user.")
