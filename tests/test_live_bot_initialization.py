import pytest
import scripts.live_bot_async as live_bot

def test_live_bot_async_core_dependencies_defined():
    """
    Ensures that all classes and modules required by the main() function 
    and SymbolBotAsync are correctly imported and available in the namespace.
    This prevents 'NameError' during bot startup.
    """
    # Classes used in main()
    assert hasattr(live_bot, 'DBManager'), "DBManager import missing in live_bot_async.py"
    assert hasattr(live_bot, 'PortfolioManagerAsync'), "PortfolioManagerAsync import missing in live_bot_async.py"
    assert hasattr(live_bot, 'TelegramNotifier'), "TelegramNotifier import missing in live_bot_async.py"
    assert hasattr(live_bot, 'BinanceWebSocketManager'), "BinanceWebSocketManager import missing in live_bot_async.py"
    
    # Core strategy engine
    assert hasattr(live_bot, 'TrendCrusherV2'), "TrendCrusherV2 import missing in live_bot_async.py"
    
    # Essential modules
    assert hasattr(live_bot, 'ccxt'), "ccxt import missing in live_bot_async.py"
    assert hasattr(live_bot, 'pd'), "pandas import missing in live_bot_async.py"
    assert hasattr(live_bot, 'asyncio'), "asyncio import missing in live_bot_async.py"

def test_symbol_bot_async_instantiation_integrity():
    """
    Checks if SymbolBotAsync can be instantiated without immediate NameErrors
    referring to global dependencies.
    """
    from unittest.mock import MagicMock
    
    mock_exchange = MagicMock()
    mock_pm = MagicMock()
    mock_notifier = MagicMock()
    mock_db = MagicMock()
    
    # This would fail if TrendCrusherV2 or other class-level refs are missing
    bot = live_bot.SymbolBotAsync("BTC/USDT", mock_exchange, mock_pm, mock_notifier, mock_db)
    assert bot.symbol == "BTC/USDT"
    assert bot.engine is not None
