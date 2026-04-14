# Changelog

All notable changes to the TrendCrusher project will be documented in this file.

## [13.1.11] - 2026-04-14
### Fixed
- **Trailing SL Persistence Bug**: Fixed a critical issue where the trailing stop loss calculated by the strategy engine was not being saved to the bot's state. This prevented the live bot from synchronizing updated stop-loss levels to the exchange.
- **Stop-Loss Synchronization Deadlock**: Implemented a **Fail-safe Market Exit** mechanism. If the price hits a newly updated trailing stop price before the bot can synchronize it with the exchange, the bot now triggers an immediate market exit to protect profits and prevent a deadlock.

### Added
- **Real-time SL Update Notifications**: Added Telegram notifications that trigger specifically when the trailing stop loss is successfully updated on the exchange. The message includes the new SL price and the current Mark Price for transparency.
- **Unit Test for SL Persistence**: Added `tests/test_trailing_update.py` to verify that the strategy engine correctly persists trailing SL updates to the state.

## [13.1.10] - 2026-04-06
### Refactored
- **Event-Driven Exit Architecture**: Removed redundant market exit orders from `check_exit`. The bot now solely relies on the exchange's SL (StopLoss) trigger and processes the resulting `FILLED` event via WebSocket, effectively eliminating race conditions and double-ordering bugs.
- **Fail-safe Syncing**: Integrated automatic `sync_all_orders` and emergency `execute_exit` as a fallback mechanism if a position exists but no corresponding SL order is found on the exchange.

### Fixed
- **Order-ID Agnostic Exit**: Enhanced `on_order_update` to recognize any position-reducing fills (opposite side) as a valid exit, even if the `order_id` doesn't match the bot's stored ID (e.g., due to manual edits or exchange re-assignment).

### Verified
- **Full Test Suite Success**: All 75 unit, integration, and E2E simulation tests are passing, confirming the integrity of the new event-driven core and robustness against ZeroDivisionErrors.

## [13.1.9] - 2026-04-06
### Fixed
- **ZeroDivisionError Protection**: Implemented comprehensive guards against `float division by zero` in PnL calculations. Added safety backups using `last_price` when Binance API returns 0 as the execution price for `STOP_MARKET` orders.
- **State Cleanup**: Enhanced position state reset logic to ensure `entry_price`, `sl_price`, and `max_price_seen` are correctly zeroed out upon trade closure, preventing stale data from affecting subsequent calculations.
- **Ambush Fill Resilience**: Added specific handling for WebSocket and Polling fill updates to ensure `entry_price` is never set to 0 even during high volatility API lags.

### Added
- **Dashboard Symbol Filtering**: The dashboard now strictly filters `live_monitors` to only display symbols currently active in `CONFIG['SYMBOLS_LIST']`.
- **Emergency Recovery Utility**: Created `scripts/emergency_recovery.py` to allow manual database state reset for specific symbols in case of persistent out-of-sync conditions.

## [13.1.8] - 2026-04-02
### Fixed
- **Binance Trigger Orders**: Implemented dedicated handlers for Binance Futures conditional orders (`STOP_MARKET`). Added `fetch_trigger_order` and `cancel_trigger_order` with `trigger: True` parameters, as these orders are not accessible via standard endpoints.
- **Order Safety**: Introduced `create_reduce_only_market_order` to strictly enforce `reduceOnly: True` when closing positions, preventing accidental position flips.
- **Logic Consistency**: Updated all entry/exit methods to use the new trigger-aware and reduce-only wrappers.

## [13.1.7] - 2026-04-02
### Fixed
- **Dashboard EMA Visualization**: Fixed the issue where the EMA line would unnaturally drop at the "Now" data point. The bot now stores the actual calculated EMA value in the `live_indicators` table, and the dashboard uses this value instead of a midpoint approximation.
- **Database Schema**: Added `ema_value` column to the `live_indicators` table with automatic migration support.

## [13.1.6] - 2026-04-02
### Optimized
- **Static Donchian Breakout**: Updated `calculate_donchian` to use `shift(1)`. This ensures that breakout levels are based strictly on previous candles, preventing the "vanishing breakout" effect where bands move alongside current price. This provides more reliable entry points for Sniper (Maker) orders.

## [13.1.5] - 2026-04-02
### Fixed
- **Persistence Logic**: Fixed `TypeError` in `DBManager.save_bot_state` by updating the method signature to accept `sniper_order_id` and `retest_order_id`.
- **Order Sync Resilience**: Improved `check_sniper_fill` and `check_retest_fill` to gracefully handle `ccxt.OrderNotFound` (Binance error -2013). The bot now clears stale order IDs from its state and database instead of retrying indefinitely.

## [v13.1.4] - 2026-04-01
### Added
- **Real-time Chart Extension**: The dashboard chart now appends the current in-progress candle data from `live_indicators` to the historical data from `history_1h`.
- **Live Labeling**: Added a "Now" timestamp label for the latest data point to differentiate it from closed candles.
- **Indicator Sync**: Real-time Price, Donchian Channels, ADX, and scaled Volume are now visible on the chart without waiting for the hour to close.

## [v13.1.3] - 2026-04-01
### Fixed
- **Dashboard Timezone**: All charts (individual symbols and portfolio equity) now display timestamps in KST (UTC+9) for easier monitoring.
- **Hourly Logging Logic**: Fixed a bug where charts only updated every 4 hours. Data is now logged correctly at the close of every 1-hour signal candle.
- **Portfolio Value Display**: Confirmed fallback logic for SEED value when equity history is empty.

## [v13.1.2] - 2026-03-31
### **🚀 Macro Visualization & UX Finalization**
- **Advanced Macro Charting**: Replaced tick charts with 48h macro charts featuring Price, EMA 200, Donchian High/Low, ADX Strength, and Volume.
- **Alphabetical Sorting**: Fixed dashboard issue where coin cards kept switching positions; now strictly sorted by symbol name.
- **Robust Backfilling**: Implemented 48h indicator backfilling with correct strategy engine column mapping and index-based timestamping.
- **System Stability**: Fixed critical SyntaxError in `db_manager.py` and optimized WebSocket event handling for high-frequency updates.

## [12.9.2] - 2026-03-31
### **🔧 Critical Dashboard & Event Handling Fix**
- **Flexible Symbol Matching**: Optimized `ws_loop` to match symbols both with and without slashes (e.g., `ETH/USDT` vs `ETHUSDT`), fixing the issue where some symbols' indicators were missing on the dashboard.
- **Instant Monitoring**: Forced an initial `live_status` record to the DB immediately after bot initialization, ensuring all coins appear on the dashboard upon startup.
- **Version Maintenance**: Upgraded to **12.9.2**.

## [12.9.1] - 2026-03-31
### **🔧 Dashboard Fix & Minor Refinements**
- **Fixed Live Indicators**: Restored dashboard indicator status by handling `markPriceUpdate` events in the `ws_loop`.
- **Improved Data Pipeline**: Ensured that the real-time price updates trigger DB status recordings for each symbol.
- **Maintenance**: Synced system version to **12.9.1**.

## [12.9.0] - 2026-03-31
### **🚀 Resilience & Reliability Overhaul**
- **Official Binance Connector Integration**: Replaced raw WebSocket implementation with the official `binance-futures-connector` library for industrial-grade stability.
- **Resilient ListenKey Lifecycle**: Implemented automatic `listenKey` renewal and immediate re-issuance on failure, ensuring Private Streams never expire.
- **Gap-Filling Order Sync**: Added `WS_RECONNECTED` event handling that triggers a full REST API order status synchronization (`fetch_order`) after any connection drop.
- **Account-wide Order Logging**: Introduced `log/account_orders.log` to record EVERY order update across the entire Binance account, enhancing auditability and manual trade tracking.
- **Type-Safe ID Management**: Fixed `order_id` type mismatch between CCXT (string) and Binance WebSocket (integer) to prevent missed fill detections.
- **Heartbeat & Reconnection**: Standardized Ping/Pong handling and 24h session renewal logic.

## [v12.8.4] - 2026-03-31
### Enhanced
- **Detailed Status Reporting**: Upgraded the `/status` command to provide a full technical breakdown per symbol, including Current Price vs. EMA 200, Donchian Bands, Volume/ADX targets, and Breakout Proximity (%).
- **Notification Reliability**: Restored missing Telegram alerts in the `force_exit` logic, ensuring users receive immediate confirmation during emergency liquidations.
### Fixed
- **Code Integrity**: Resolved critical `IndentationError` and removed corrupted code fragments at the end of `live_bot_async.py`.
- **Runtime Stability**: Fixed an `is_live` name error in the real-time indicator update loop.

## [v12.8.3] - 2026-03-31
### Added
- **Stream-based WebSocket Engine**: Upgraded `BinanceWebSocketManager` with an `async generator` (`stream()`) for modern `async for` loop compatibility, reducing message processing latency.
- **Automated ListenKey Management**: Integrated private User Data Stream support. The bot now automatically fetches, manages, and keeps alive the Binance `listenKey` for real-time `ORDER_TRADE_UPDATE` events.
- **Enhanced Configuration Fallbacks**: Added hardcoded default for `EXCHANGE: "binance"` in `config.py` to prevent crashes when the key is missing from `config.yaml`.
### Fixed
- **WebSocket Compatibility**: Restored `get_next_message()` and immediate URL construction to maintain full compatibility with the existing 71-test suite.

## [v12.8.2] - 2026-03-30
### Added
- **Persistent Ambush Tracking**: Expanded the DB schema to store `active_sniper_order_id` and `active_retest_order_id`. The bot now recovers pending ambush orders upon restart, ensuring no fill is ever missed.
- **Diagnostic Logging**: Implemented comprehensive logging for every order update received via WebSocket to provide full transparency into the exchange communication.
- **Redundant Fill Polling**: Added a 30-second fallback polling mechanism that checks exchange order status to safeguard against potential WebSocket message loss.
### Fixed
- **Force Exit Precision**: Updated `force_exit()` to record trade closure in the database and calculate PnL even during emergency liquidations.
- **Runtime Stability**: Fixed an `is_live` name error in the indicator update loop and cleaned up duplicated entry points.

## [v12.8.1] - 2026-03-29
### Optimized
- **Sniper Entry Engine**: Replaced `LIMIT` orders with `STOP_MARKET` for Sniper mode. This prevents premature Taker fills when placing orders above/below current market price and ensures entry only occurs at the exact breakout level.
- **Price Precision**: Integrated Binance WebSocket `ap` (Average Price) field for real-time order updates, providing bit-perfect entry prices for the dashboard and PnL tracking.
### Fixed
- **Dashboard Synchronization**: Fixed a state persistence gap where Sniper fills via WebSocket weren't immediately reflected on the dashboard. Forced DB sync now occurs immediately upon `FILLED` status.
- **Test Integrity**: Updated the 71-test suite to validate `STOP_MARKET` parameters and positional arguments through the API retry wrapper.

## [v12.8.0] - 2026-03-25
### Security
- **Dashboard Hardening**: Restrained Flask host to `127.0.0.1` and disabled `debug` mode to prevent unauthorized remote access and potential RCE via interactive debugger.
- **Path Traversal Protection**: Implemented strict path normalization and validation for report file serving. Access is now limited exclusively to the `reports/` directory using absolute path checks.
### Fixed
- **Portfolio Value Sync**: Corrected the dashboard's "PORTFOLIO VALUE" display to reflect real-time cumulative PnL combined with the initial seed. 
- **Equity History Isolation**: Fixed chart data to correctly filter by `symbol='TOTAL'`, preventing data mixing with individual asset performance logs.

## [v12.7.0] - 2026-03-25
### Optimized
- **Mega-Turbo Parallel Optimizer**: Re-architected the `mega_optimizer_v2.py` to use a task-level parallelization strategy. By breaking down the optimization grid into individual (Symbol + Params) tasks, the bot now achieves near-perfect CPU utilization across all cores.
- **Engine Consolidation**: Fully integrated the Numba-accelerated streaming engine into the global optimizer, ensuring that the fastest available code is used for exhaustive parameter searches.

## [v12.6.0] - 2026-03-25
### Optimized
- **Vectorized Jump Exit Engine**: Implemented `while`-loop based jump logic for position-held periods. Instead of per-minute checks, the engine now uses `numba_find_first_exit` to skip straight to the exit timestamp, significantly accelerating long-term simulation runs.
- **Precision Equity Reconstruction**: Refined the equity curve backfilling logic during jumps to ensure that Max Drawdown (MDD) and daily equity logs are bit-for-bit identical to non-optimized versions.

## [v12.5.0] - 2026-03-25
### Optimized
- **Numba JIT Accelerated Engine**: Applied `@njit` (Just-In-Time) compilation to core trading logic (`check_entry_signal`, `check_exit_signal`). This achieves C-level execution speed for the backtest loop, providing a massive performance boost for parameter optimization.
- **Pure NumPy Interface**: Refactored internal signal handlers to work exclusively with primitive NumPy arrays, removing Python interpreter overhead from the hot-path of simulation.

## [v12.4.0] - 2026-03-25
### Optimized
- **NumPy Turbo Backtest Engine**: Re-engineered the `run_streaming_backtest` core loop using raw NumPy array operations. This drastically improves simulation speed (up to 8x faster) by eliminating Pandas indexing overhead and memory fragmentation.
- **Fast Index Lookup**: Implemented `searchsorted` based timestamp-to-index mapping for zero-lag indicator reference in minute-by-minute backtests.
- **Invariant Verification**: Guaranteed bit-for-bit identical results with previous versions while achieving significant performance gains.

## [v12.3.0] - 2026-03-25
### Fixed
- **Order Response Guard**: Implemented comprehensive defensive logic for `order.get()` calls in `live_bot_async.py` and `live_bot_multi.py`. This prevents crashes if the exchange returns `None` due to timeouts or API instability.
- **Nested Fee Safety**: Added safety checks for nested `fee` dictionary objects, ensuring consistent fallback when fee data is missing.
### Changed
- **Indicator Engine Refinement**: Updated Donchian Channel calculation to remove redundant shifts, improving signal alignment for the Unified Strategy Engine.
- **WebSocket Resilience**: Added support for Binance User Data Streams (private WS) and implemented exponential backoff for reconnection stability.

## [v12.2.0] - 2026-03-25
### Added
- **Margin Safety Guard**: Real-time balance verification before any entry. The bot automatically downsizes quantities if required margin exceeds available balance (95% safety threshold).
- **Multi-Currency Support**: Enhanced balance checking for both USDT and USDC settlement pairs based on symbol attributes.

## [v12.1.0] - 2026-03-25
### Added
- **Anti-Drift Sync (V4)**: Bi-directional synchronization between local bot state (DB) and exchange positions.
- **Telegram Manual Sync**: Added `/sync` command to force a state check across all symbols via Telegram.

## [v12.0.0] - 2026-03-25
### Added
- **Private WebSocket Integration**: Real-time order update tracking via Binance `ORDER_TRADE_UPDATE` events, reducing API polling overhead and improving fill detection speed.
- **Incremental Calculation Engine**: Optimized indicator calculation in live mode to only process tail-end data, drastically reducing CPU and memory footprint during high-volatility events.
- **Performance Throttling**: Implemented controlled update intervals for DB persistence and Dashboard synchronization.

## [v11.9.10] - 2026-03-25
### Added
- **Automatic DB-Exchange Sync**: The bot now performs a synchronization check at startup. Any 'OPEN' trades in the database that no longer exist as active positions on Binance are automatically closed to prevent "ghost positions" on the dashboard.
- **State Alignment**: Bot internal state is now rigorously aligned with the actual exchange balance during the boot sequence.

## [v11.9.9] - 2026-03-25
### Fixed
- **Exit Verification Logic**: Overhauled `execute_exit` to verify position closure via API before resetting internal state.
- **Self-Healing Exit**: Implemented automatic retry with exact remaining contracts if a market exit partially fails or the exchange reports a residual balance.

## [v11.9.8] - 2026-03-25
### Added
- **Turbo-Charged NumPy Engine**: Refactored the core backtest loop in `src/strategy.py` using NumPy vectorization, achieving a ~5x speedup in simulation performance.
- **Microsecond Precision Matching**: Fixed timestamp alignment issues between 1m ticks and 1h indicators using standardized NumPy `datetime64[m]` casting.
- **Smart Optimizer Resume**: The mega optimizer now recursively scans ALL previous session folders to prevent redundant calculations, making it truly "overnight-safe."
- **Financial Parity**: Differentiated Maker (0.02%) and Taker (0.05%) fees in the backtest engine to match real-world Binance Futures accounting.

### Fixed
- **Adaptive Indicator Warmup**: Implemented automatic EMA period reduction for symbols with short historical data (e.g., XAU), preventing indicator dropouts.
- **Zero-Trade Bug**: Resolved a critical issue where optimizations returned 0 results due to strict trade count filters and misaligned dataframes.

## [v11.9.4] - 2026-03-23
### Added
- **Hyper-Precision PnL Tracking**: The bot now fully synchronizes its internal PnL calculation with the exchange's actual execution data (`average` price and real `fee`), completely eliminating discrepancies caused by slippage.
- **Independent SEED Equity Tracking**: Equity curves and dashboard balances are now strictly calculated based on the internal `SEED` plus cumulative realized PnL. This prevents cross-contamination from manual trades or other bots using the same Binance account.
- **Multi-Symbol Overnight Optimizer**: Added `scripts/mega_overnight_optimizer.py`, a multiprocessing-powered tool that concurrently tests exhaustive parameter grids across multiple symbols (ETH, BTC, SOL, XRP, TRUMP, XAU) partitioned by 90-day quarters.

## [v11.9.1] - 2026-03-23
### Fixed
- **Emergency Shutdown Logic**: Completely overhauled the `/close_all` command. It now uses `force_exit()` to check actual exchange positions via API and close them regardless of internal bot state.
- **Async Synchronization**: Implemented `asyncio.gather` for emergency shutdown tasks to ensure all closure orders are dispatched before the process terminates.
- **ZeroDivisionError**: Fixed a crash in `execute_exit()` when calculating PnL if `entry_price` was zero or uninitialized.

## [v11.9.0] - 2026-03-23
### Added
- **Signal Hysteresis (Ambush Stability)**: Introduced a 20% hysteresis buffer for Volume and ADX filters when an order is already active (Ambushing). This prevents "order spam" and unnecessary cancellations caused by minor intra-bar flickering.
- **Dynamic Proximity Hysteresis**: Expanded the Sniper proximity threshold from 0.5% to 1.0% once a limit order is placed, allowing for small price fluctuations without losing the ambush position.
- **Volume Burst Persistence**: Added `prev_volume` and `prev_avg_vol` tracking to indicators. The system now maintains a signal if a volume burst occurred in the previous bar, preventing " 정각(top-of-the-hour)" signal loss when new candles start with zero volume.
- **Stabilized Backtest Engine**: Synchronized `run_precision_backtest` and `run_streaming_backtest` with live hysteresis logic for 100% behavior parity.
- **New Test Suite**: Added `tests/test_hysteresis_persistence.py` to verify all stabilization edge cases.

## [v11.8.0] - 2026-03-22
### Added
- **Look-ahead Bias Removal**: Introduced `run_streaming_backtest` in `TrendCrusherV2`, a minute-by-minute simulation that reconstructs developing indicators exactly as the live bot does.
- **Hyper-Optimized Simulator**: Achieved 100x speedup in streaming backtests by pre-calculating indicators and using index-based access, allowing 365-day 1m simulations to finish in minutes.
- **Comprehensive Visual Reporting**: Automatically generates 4-panel PNG charts (Price, ADX, Volume, Equity Curve) with embedded strategy parameters for every realistic simulation run.
- **Structured Report Storage**: Results are now organized in a hierarchical folder structure: `reports/{SYMBOL}/{MODE}/{TIMESTAMP}/` for easier comparison.
- **Incremental Data Sync**: `BinanceDataFetcher` now supports appending new data to existing files, drastically reducing update times.
- **Single Source of Truth**: Unified the core strategy logic into `TrendCrusherV2` shared by live trading and all simulation tools.
### Changed
- **Dashboard Recursive Scan**: Updated the Flask UI to recursively find and display all backtest files across the new structured directory.
- **Improved MARKET Entry**: Market mode now uses real-time `last_price` instead of previous candle close for better signal accuracy in live environments.
### Fixed
- **Floating Point Edge Cases**: Added an epsilon buffer to Sniper proximity checks to ensure reliable triggers during high-speed breakouts.
- **DB Migration Safety**: Verified automatic `sl_price` column creation for seamless upgrades from older versions.
- **100% Test Pass Rate**: Fixed and modernized the entire 59-test suite to align with the new modular engine.

## [v11.7.0] - 2026-03-22
### Added
- **Equity Curve Visualization**: Integrated Chart.js in the dashboard for real-time portfolio performance tracking.
- **Enhanced Market Pulse**: Added 24h percentage change and real-time prices for watched symbols on the dashboard.
- **E2E Simulation Suite**: Introduced `test_e2e_simulation.py` to verify full trading cycles (entry -> trail -> exit).
- **WebSocket Resilience Tests**: Comprehensive verification of reconnection and message queuing in `test_websocket.py`.
### Changed
- **Dashboard UI Refinement**: Modernized professional dark theme for the Flask terminal.
- **Test Modernization**: Refactored `test_risk_safety.py` and `test_strategy_v2.py` to align with the async engine and blackbox testing principles.
### Fixed
- **Strategy Mirror Testing**: Eliminated redundant logic duplication in tests by switching to outcome-based verification.
- **Async Risk Logic**: Ensured leverage and precision rules are correctly applied in the `SymbolBotAsync` context.

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
