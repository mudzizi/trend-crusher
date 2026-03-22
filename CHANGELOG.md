# Changelog

All notable changes to the TrendCrusher project will be documented in this file.

## [v11.6.0] - 2026-03-22
### Added
- **Symbol-Aware Relative Adaptive Trail**: Introduced `tighten_ratio` in `ADAPTIVE_TRAIL_STEPS`. This allows the trailing stop to tighten as a percentage of the symbol's unique base ATR multiplier, maintaining each asset's "personality" while protecting profits.
- **Improved Default Steps**: Updated configuration examples to use realistic profit-taking intervals (1.5%, 3.0%, 5.0%) based on live market observations.
### Changed
- Refactored `src/strategy.py` to support both legacy `atr_mult` and the new `tighten_ratio` for backward compatibility.

## [v11.5.0] - 2026-03-22
### Added
- **Retest Maker Mode (True Maker)**: Implemented a new entry strategy that waits for a price pullback (retest) to the breakout level after a signal, enabling 100% Maker fills.
- **Differentiated Fee Structure**: Introduced a realistic fee model applying Maker fees (0.02%) vs Taker fees (0.05%) based on the chosen entry mode.
- **3-Way Strategy Duel**: The optimizer now compares **Market**, **Sniper**, and **Retest Maker** modes to identify the most efficient entry method for each asset.
- **Timeout Management**: Added a 4-hour window for Retest Maker orders to prevent entries on stale or weakened signals.
### Changed
- **Performance Breakthrough**: Confirmed that `Retest Maker` significantly reduces MDD (Drawdown) for assets like BTC by filtering out high-slippage entries.
- **Realized Results**: All backtesting now reflects real-world Taker fees for breakout-style entries by default.

## [v11.4.0] - 2026-03-21
### Added
- **Sniper vs Market Dual-Optimization**: The backtesting engine now supports both Sniper (Limit Entry) and Market (Close-based Entry) modes.
- **Intra-bar Breakout Simulation**: Implemented granular price movement tracking in `run_precision_backtest` to accurately simulate Sniper entries at precise Donchian levels.
- **Automated Mode Selection**: The optimizer now automatically identifies and proposes the best entry mode (Sniper or Market) for each symbol based on historical efficiency.
- **Enhanced Sentinel Reports**: Telegram and CSV reports now include the "Mode" field to guide users on the best strategy for each asset.

## [v11.3.0] - 2026-03-21
### Added
- **Mega-Optimizer V2**: High-performance parallelized optimization engine using `ProcessPoolExecutor` for 10x faster backtesting.
- **Advanced Parameter Grid**: Expanded optimization to include `ADX_FILTER_LEVEL`, `DONCHIAN_PERIOD`, and `EMA_TREND_PERIOD` alongside Volatility and Trailing ATR.
- **Unified Symbol Discovery**: Integrated `get_top_symbols` into `BinanceDataFetcher` for consistent high-volume asset identification across the system.
- **The Sentinel Proposal**: Automated Telegram reporting of Top 3 high-potential symbols with their optimal configurations after each run.
### Changed
- **Optimized Discovery Period**: Set the default backtesting window to 90 days for improved relevance to current market volatility.
- **Enhanced Strategy Interface**: Modified `TrendCrusherV2.run_precision_backtest` to support direct parameter injection for more granular optimization control.
- **Robust Symbol Filtering**: Improved `BinanceDataFetcher` to correctly handle `/:` symbol formats and exclude non-standard or leveraged tokens.

## [v11.2.0] - 2026-03-21
### Added
- **Real-time OHLCV Updates**: Modified `SymbolBotAsync` to update OHLCV buffers in real-time (2s interval) via WebSocket kline streams. This eliminates the delay caused by waiting for candle closes and ensures volume-based and breakout signals are triggered instantly.
- **Telegram Command Buttons**: Added a clickable command menu and bottom reply keyboard for easy bot control (status, sniper_on/off, stop/resume, close_all).
- **Configuration Overhaul (YAML)**: Transitioned entire system to YAML-based configuration (`config.yaml`) with environment variable overrides for better security and flexibility.
- **1-Minute Logging Heartbeat**: Periodic logging in `heartbeat_loop` for improved system health visibility.
- **Timeframe Filtering**: Implemented strict filtering to ignore irrelevant kline streams, preventing buffer corruption.
- **Documentation**: Created `CONFIG_GUIDE.md` and updated `STRATEGY_WHITEPAPER.md` to reflect the new real-time engine.
- **Enhanced Testing**: Added `tests/test_async_realtime.py`, `tests/test_config_loading.py`, and `tests/test_telegram_buttons.py` for full verification of new features.
### Fixed
- **Resilience Test Regression**: Updated tests to align with new engine logic and method signatures.
- **Latency Optimization**: Reduced response time to ~1-2s for all trading conditions.

## [v11.1.1] - 2026-03-21
### Added
- **Command Flushing**: Implemented a startup flush mechanism for Telegram commands to ignore old messages (e.g., `/close_all`) sent while the bot was offline.
- **Enhanced Testing**: Expanded `tests/test_resilience.py` to verify command flushing logic.
- **Version Synchronization**: Centralized versioning in `src/config.py`. Replaced all hardcoded version strings across logs, reports, and documentation with dynamic references to `CONFIG['VERSION']`.
### Fixed
- **Legacy String Cleanup**: Removed remaining "V3" hardcoded strings in `scripts/live_bot.py` and other legacy areas.
- **Test Fixture Stability**: Fixed `KeyError: 'VERSION'` in `tests/test_sentinel.py` by ensuring mock configurations include the version key.
- **Startup Crash Prevention**: Resolved a potential issue where old shutdown commands could trigger an immediate exit upon restart.

## [v11.1.0] - 2026-03-21
### Added
- **Network Resilience**: Integrated `retry_api_call` into `fetch_ohlcv` to automatically recover from transient Binance API timeouts and network errors.
- **Fault-Tolerant Loop**: Wrapped the main event loop in a try-except block to prevent the entire bot from crashing due to individual message processing errors.
- **Resilience Testing**: Added `tests/test_resilience.py` to verify API retry logic and startup error handling.
### Changed
- **NumPy Downgrade**: Downgraded NumPy to `v1.26.4` to resolve `AttributeError: _ARRAY_API not found` and ensure compatibility with `pandas` and `pyarrow`.
- **Environment Stability**: Updated `requirements.txt` to lock NumPy at `v1.x` and prevent future breaking upgrades.

## [v11.0.1] - 2026-03-21 (Current)
### Added
- **Resilience Watchdog**: Implemented `scripts/watchdog.py` to monitor the bot process and auto-restart on crashes or OOM Killer events.
- **Last Will Notification**: Added global exception and signal handlers to notify via Telegram immediately before a crash or termination.
- **Resource Protection**: Ensured explicit closure of exchange connections during shutdown to prevent resource leaks.
- **Stability Fixes**: Resolved various SyntaxErrors and verified the entire suite with 34/34 tests.

## [v11.0.0] - 2026-03-21
### Added
- **The Sniper (Pre-emptive Limit Entry)**: Places zero-offset Maker Limit orders precisely at Donchian breakout levels when price approaches within 0.5%.
- **4-Pillar Strict Validation**: Ambush is only set if Proximity, Volume Burst, ADX Trend, and EMA Macro-direction align perfectly.
- **Ruthless Abort Logic**: Instantly cancels the unfilled Limit Order if any of the 4 Pillars weaken to avoid fakeout traps.
- **Atomic Transition**: Automatically secures the position with a Server-side SL the moment the Sniper order is filled.
- **Sniper Kill Switch**: Added `/sniper_on` and `/sniper_off` to Telegram commands for manual override.

## [v10.0.0] - 2026-03-21
### Added
- **The Sentinel (Hybrid Optimization)**: Automated weekly/performance-based optimization proposals with manual approval queue.
- **Interactive Command Validator**: Standalone tool (`scripts/test_telegram_commands.py`) to verify remote connectivity and authorization.
- **Command Set Expansion**: Added `/apply [SYMBOL]`, `/reject [SYMBOL]`, and enhanced `/status` with pending proposal indicators.
- **Refined Unit Tests**: 31/31 tests passing, including comprehensive Sentinel and Authorization logic.

## [v9.0.0] - 2026-03-21
### Added
- **Self-Adaptive Optimizer Engine**: Implemented "Walk-Forward" optimization to re-calibrate parameters based on recent 30-day market data.
- **Remote Optimization Control**: Added `/optimize [SYMBOL]` command via Telegram to trigger real-time parameter tuning.
- **Settings Hot-Reload**: Enabled live updates of `VOL_MULTIPLIER`, `ADX_FILTER`, and `EMA_PERIOD` without restarting the bot.
- **Efficiency Ranking**: Parameters are now selected based on `Return / MDD` ratio rather than pure profit.

## [v8.0.0] - 2026-03-21
### Added
- **Command & Control System**: Bidirectional Telegram communication for remote bot management.
- **Interactive Commands**: Added `/status`, `/stop`, `/resume`, and `/close_all` (Emergency Kill Switch).
- **Hourly Heartbeat**: Automated portfolio health reports delivered every hour.
- **Enhanced Security**: Authorized command execution limited to specific `TELEGRAM_CHAT_ID`.

## [v7.0.1] - 2026-03-21
### Added
- **Atomic Order Safety**: Immediate liquidation if Stop-Loss (SL) placement fails after entry.
- **Fault-Tolerant Error Handling**: Categorized exceptions (Network, Budget, Terminal) with smart retry/panic protocols.
- **Async Resilience**: Improved SL cleanup on position exit to prevent ghost orders.

## [v7.0.0] - 2026-03-21
### Added
- **WebSocket Async Engine**: Migrated to `asyncio` and WebSocket streaming for near-zero latency data.
- **Real-time Tick Processing**: Millisecond-level signal detection for entries and trailing stops.
- **Async Portfolio Manager**: Thread-safe capital allocation using `asyncio.Lock`.

## [v6.2.0] - 2026-03-20
### Added
- **Formal Version Management**: Integrated `VERSION` constant across logs, Telegram, and Dashboard.
- **v6.2.0 Release**: Standardized system identification.

## [v6.0.0] - 2026-03-20
### Added
- **Smart Isolated Margin**: Automated 'Isolated' margin setup for new trading pairs.
- **Independent Capital Isolation**: `ALLOCATED_SEED` per symbol ensures profit/loss stays within each coin's sub-ledger.
- **Enhanced Persistence**: Full state recovery (max_price, sl_order_id) from DB across restarts.

## [v5.0.0] - 2026-03-20
### Added
- **Safety & Resilience Upgrade**: Integrated `bot_state` persistence and real-time Available Margin checks.
- **API Retry Logic**: Robustness against transient network failures.

## [v4.0.0] - 2026-03-20
### Added
- **Multi-Symbol Portfolio Manager**: Centralized capital allocation engine.
- **Symbol-Specific Optimization**: Individual parameters (VOL_MULT, EMA_PERIOD) for TRUMP, ETH, XAU.
- **Portfolio Dashboard**: Advanced web UI for real-time monitoring of all active positions.

## [v3.0.0] - 2026-03-20
### Added
- **ADX Filter**: Trend strength validation to filter out chop-saw market conditions.
- **Adaptive Trailing Stop**: Dynamic ATR-based exit logic that tightens as profit increases.

## [v2.0.0] - 2026-03-19
### Added
- **Trend & Volatility Filters**: Integrated 4h EMA trend filter and Volume Burst detection.
- **Precision Backtester**: 1-minute intra-bar validation for realistic results.

## [v1.0.0] - 2026-03-18
### Added
- **Initial Core Engine**: Donchian Channel breakout strategy for single-symbol trading.
- **Basic DB & Logging**: Persistence for trade history and equity tracking.
