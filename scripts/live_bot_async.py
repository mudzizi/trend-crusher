import asyncio
import ccxt.async_support as ccxt
import pandas as pd
from src.bot.live_bot_async import main, SymbolBotAsync, handle_commands
from src.async_db_manager import AsyncDBManager as DBManager
from src.portfolio_manager_async import PortfolioManagerAsync
from src.telegram_utils import TelegramNotifier
from src.websocket_manager import BinanceWebSocketManager
from src.strategy import TrendCrusherV2


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal: {e}")


