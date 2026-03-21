# Changelog

All notable changes to the TrendCrusher project will be documented in this file.

## [v11.1.2] - 2026-03-21
### Added
- **Real-time OHLCV Updates**: Modified `SymbolBotAsync` to update OHLCV buffers in real-time (2s interval) via WebSocket kline streams. This eliminates the delay caused by waiting for candle closes and ensures volume-based and breakout signals are triggered instantly.
- **Async Real-time Testing**: Added `tests/test_async_realtime.py` to verify real-time buffer updates and trigger mechanisms.
### Fixed
- **Resilience Test Regression**: Updated `tests/test_resilience.py` to align with the new `on_kline_update` method signature and internal logic.
- **Latency Optimization**: `check_entry` and `check_exit` now react to every price/volume update instead of only on candle close or mark price updates.

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
