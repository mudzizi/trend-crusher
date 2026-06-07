import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import asyncio
from src.config import CONFIG

# Configure logging before importing anything that configures basicConfig
os.makedirs("log", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler("log/live_bot.log"),
        logging.StreamHandler()
    ]
)

# Override SYMBOLS_LIST to only run the single SYMBOL configured
CONFIG["SYMBOLS_LIST"] = [CONFIG.get("SYMBOL", "BTC/USDT")]

from src.bot.live_bot_async import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal: {e}")
