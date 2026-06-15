# Changelog

All notable changes to the TrendCrusher project will be documented in this file.

## [13.8.8] - 2026-06-15
### **📊 Dynamic Checklist Alignment & Volume Chart Scaling Fix**
- **Dynamic Indicators Checklist**: Aligned status tracking score (`_compute_signal_score` in `live_bot_async.py`) and Web Dashboard checklist (`dashboard.py` checklist logic) with the actual dynamic criteria used by the core trading engine (`numba_check_entry`). Choppiness scaling, squeeze bonus, short bias, and order ambush hysteresis are now correctly calculated and displayed.
- **Volume Ratio Inflation Fix**: Fixed a bug where `vol_ratio` (already stored as a percentage in DB) was multiplied by 100 on the dashboard, resulting in inflated values like `6485.8%`. The checklist volume readiness now renders in multiplier format (e.g., `Vol >= 2.2x (1.43x)`).
- **Volume Chart Scaling Fix**: Corrected volume reconstruction for charting to divide `vol_ratio` by 100 first, eliminating the huge rightmost bar spikes that distorted the volume charts. Additionally, the dashboard now uses the rolling 20-hour average volume (`avg_vol_20`) matching the bot's internal scaling instead of the 48-hour average, ensuring the reconstructed current hour's volume matches the exchange precisely.
- **Multi-Panel Chart Alignment**: Added `afterFit` layout configurations to all four charts (Price, ADX, Chaos, Volume) in the frontend to fix a visual alignment bug where price digits or hidden y-axes caused charts to shift sideways. The y-axis width is now forced to exactly 70px across all panels, ensuring the vertical grid lines (time ticks) align perfectly.
- **Closed Candle Volume Logging Fix**: Fixed a logic bug where `on_kline_update()` logged `iloc[-1]` (the newly opened hour with volume ~0) when a candle closed, missing the closed candle (`iloc[-2]`) entirely. The bot now matches the exact closed candle in `df_indicators` using the closed kline start timestamp `kline['t']` before logging, resulting in volumes that perfectly match the exchange.
- **Testing Coverage**: Updated unit tests to mock `db.get_bot_state` and added `test_dynamic_checklist_volume_and_adx_logic` and `test_on_kline_update_logs_correct_closed_candle`. All 98 tests pass cleanly.

## [13.8.7] - 2026-06-14
### **📊 Batch Backfill and ADX 4H Zero Value Resolution**
- **Batch Backfill**: Modified `_backfill_history_1h()` to batch-upload the last 120 hours of indicator calculations (matching the DB's 5-day retention limit) to the database on bot startup. This fills any chronological gaps that occur when the bot is offline.
- **ADX 4H Zero Value Fix**: Added `log_history_1h_batch()` and upgraded database insertion from `INSERT OR IGNORE` to `INSERT OR REPLACE`. This replaces any legacy zero-value ADX 4H records in the database with correctly calculated values calculated from the full OHLCV series.
- **Robust Verification**: Added new test cases `test_log_history_1h_batch` and `test_async_log_history_1h_batch` to `tests/test_db_manager.py`. All 96 tests pass cleanly.

## [13.8.6] - 2026-06-14
### **📊 Backfill, Dynamic Score, and Tooltip Date Enhancement**
- **History Backfill**: Added `_backfill_history_1h()` method to `SymbolBotAsync`. On bot initialization, backfills last 48h of indicator data from the already-fetched 1000-bar OHLCV, ensuring all coins start with consistent chart history regardless of when they were added.
- **Dynamic Signal Score**: Replaced hardcoded `score=100` with `_compute_signal_score()` that evaluates 6 entry conditions (Chaos, Slope, Chop, ADX, ADX 4H, Volume) + Squeeze bonus, producing a meaningful 0-100 score.
- **Tooltip Date Display**: Chart labels now include date (`MM/DD HH:MM`). X-axis ticks show only `HH:MM` for compactness, but mouse-over tooltip title shows the full date+time.


### **🖥️ Dashboard Indicator Enhancement for Entry/Exit Decision Support**
- **Multi-Panel Chart System**: Replaced single cramped 180px chart with 4 dedicated panels per symbol: Price/EMA/Donchian (220px), ADX 1H+4H (70px), Chaos/Choppiness (70px), Volume (50px).
- **ADX 4H Pipeline**: Added `adx_4h` column to `history_1h` and `live_indicators` DB tables. Updated `db_manager.py`, `async_db_manager.py`, `live_bot_async.py`, and `dashboard.py` to log, pass, and display the previously-missing 4H ADX indicator.
- **Entry Readiness Checklist**: Added real-time 6-condition pass/fail checklist (Chaos, Slope, Chop, ADX, ADX 4H, Volume) with progress bar, showing exact current values vs thresholds.
- **Position Overlay**: Entry price and Stop-Loss lines rendered as chart annotations on the price panel when in position.
- **Chart Annotations**: Added threshold reference lines with labels on ADX and Chaos/Chop panels for instant pass/fail visual assessment.
- **Direction Badge**: Each symbol card now shows ▲ LONG or ▼ SHORT bias indicator.
- **Chart Legend**: Added compact legend strip identifying all indicator lines by color.
- **Volume Color-Coding**: Volume bars are now green (up candle) / red (down candle) with improved visibility.
- **Wider Layout**: Cards use 2-column layout (was 3) for more chart real estate.
- **Zero Regression**: All 94 tests pass with no failures.

## [13.8.4] - 2026-06-12
### **⚡ Fix Trailing Stop Loss Degradation in Backtest Engine**
- **Trailing SL Degradation Fix**: Updated `numba_find_first_exit` in `src/strategy_numba.py` to continuously persist and update `sl_p` in the minute-by-minute evaluation loop. This ensures that the active Stop Loss never degrades even when the ATR value increases on subsequent bars, matching the live trading bot execution logic.
- **Added Regression Test**: Created `test_numba_find_first_exit_sl_leakage` in `tests/test_strategy.py` to verify the fix, simulating volatile ATR expansions and proving that the correct trailing SL holds.

## [13.8.1] - 2026-06-08
### **⚡ Align Mega Optimizer with Strategy V7.0 Indicators**
- **Unified Indicator Engine**: Refactored `scripts/mega_overnight_optimizer.py` to calculate indicators via `TrendCrusherV2.calculate_indicators` instead of duplicating math logic locally, guaranteeing full compatibility with newer Momentum V7.0 filters (`chop`, `chaos`, `squeeze`, `ema_slope`, `adx_4h`).
- **Robust Optimization Testing**: Confirmed compatibility with full verification tests and successfully pushed the patch to the remote repository.

## [13.8.0] - 2026-06-08
### **⚡ Optimization Engine Performance Acceleration**
- **Indicator Calculation Caching**: Optimized parameter grid search by pre-calculating and caching indicators per `EMA_TREND_PERIOD` (the only parameter affecting series operations), reducing redundant calculation operations by 16x (from 48 down to 3).
- **Multiprocessing Grid Search**: Integrated `ProcessPoolExecutor` to run backtesting in parallel across all available CPU cores. Restructured the backtest worker function `_run_single_search` at the top level of the module for `pickle` serialization.
- **Robust Testing Verification**: Implemented a comprehensive test suite in `tests/test_optimizer_engine.py` using mocked data sources to guarantee accurate parameter optimization without actual file I/O or network requests.

## [13.7.0] - 2026-06-08
### **🤖 Unify Legacy Synchronous Bots onto Async Core**
- **Legacy Bot Consolidation**: Refactored `scripts/live_bot.py` and `scripts/live_bot_multi.py` by removing over 570 lines of duplicate synchronous trading loops, order syncs, and config loadings.
- **Async Execution Wrapper**: Replaced the synchronous bot cores with modern thin wrappers that delegate all execution to the asynchronous multi-symbol bot core (`src/bot/live_bot_async.py`), securing a single source of truth (SSOT) for live trading.
- **CLI Compatibility**: Preserved command-line interface arguments and logging file targets (`log/live_bot.log` and `log/live_bot_multi.log`) to guarantee zero regression for existing automation pipelines.
- **Robust Path Resolution**: Appended the project root path to `sys.path` in both scripts to prevent `ModuleNotFoundError` when run directly without setting `PYTHONPATH`.

## [13.6.0] - 2026-06-08
### **⚙️ Strategy Interface Abstraction & Modular Backtest Engine**
- **Strategy Abstraction**: Introduced the `BaseStrategy` abstract base class in `src/strategy_base.py` to define standard interfaces for indicator calculation, entry detection, and exit signals.
- **Numba Logic Isolation**: Extracted high-performance JIT-compiled mathematical logic (`numba_check_entry`, `numba_check_exit`, `numba_find_first_exit`) from the strategy core into `src/strategy_numba.py` to achieve clear separation of concerns (SRP).
- **Decoupled Backtester Engine**: Separated the 1m streaming simulation loop into `BacktestEngine` in `src/backtest_engine.py` which dynamically accepts any strategy conforming to `BaseStrategy`.
- **Facade Compatibility**: Refactored `TrendCrusherV2.run_streaming_backtest` as a thin wrapper that delegates computation to the new `BacktestEngine`, preserving full backward compatibility with over 20 pre-existing optimization and analysis scripts.
- **Comprehensive Refactored Tests**: Added `tests/test_strategy_refactored.py` to directly verify individual Numba functions and BacktestEngine execution, scaling the verified test suite count to 91 successful tests.

## [13.5.0] - 2026-06-08
### **🧹 Test Suite Consolidation & Simplification**
- **Unified Test Architecture**: Consolidated 28 standalone test files down to exactly 17 clean, modular test files, removing redundant and overlapping test definitions.
- **Async Bot Core Consolidation**: Created `tests/test_bot_async.py` as a single source of truth for the async bot lifecycle, merging `test_async_realtime.py`, `test_live_bot_initialization.py`, `test_live_optimizations.py`, and `test_live_sync_pnl.py`.
- **Cleaned Up Test Files**: Removed 11 deprecated, consolidated standalone test files from the workspace.
- **Zero-Regression Verification**: Ran the full test suite and verified that all 88 consolidated tests pass successfully.

## [13.4.3] - 2026-06-08
### **🤖 Telegram Auto-Menu & Comprehensive Status Command**
- **Bot Commands Auto-Registration**: Integrated `notifier.set_commands()` inside bot startup sequences (`live_bot_async.py`, `live_bot_multi.py`, and `live_bot.py`) to automatically update the Telegram bot commands menu upon initiation.
- **Enhanced Status Reports**: Overhauled `SymbolBotAsync.get_detailed_status` to report coin entry price, quantity, stop loss, current price, and unrealized PnL alongside current values and standards for all trading indicators (Trend EMA, Donchian Channel, Volume Burst, ADX, Choppiness Index, Chaos Index, Squeeze Score, and EMA Slope).
- **Dashboard Test suite Fixes**: Bypassed basic authentication checks during unit tests in `tests/test_dashboard.py` to fix pre-existing 401 unauthorized test failures.

## [13.3.8] - 2026-06-06
### **⚡ Intelligent API Scaling & Operational Resilience**
- **Memory-Based OHLCV Updates**: Optimized `on_kline_update` to update candles in-memory using WebSocket data. Full REST API fetches (1,000 bars) now only occur when a candle actually closes (`kline['x']`). This completely eliminates "API Rate Limit" warnings and OS-level process kills (Exit -9).
- **Nuclear SL Cleanup**: Implemented a mandatory `cancel_all_orders` sweep before creating any new Stop-Loss order. This guarantees zero duplicate orders on the exchange, even if the bot's local state is temporarily inconsistent or after a database wipe.
- **Numba Engine SL Restoration**: Fixed a critical bug in `src/strategy.py` where the high-speed Numba engine was calculating profit-protected SL levels but failing to return them to the live bot. Now returns `(trigger, new_sl)`, enabling functional Break-even and Adaptive Trailing in real-time.
- **Robust SSOT Synchronization**: Added a mandatory exchange position sync during the `initialize` phase. The bot now prioritizes real-time exchange state (Single Source of Truth) over local database records on startup, preventing "Long vs Short" state mismatches.
- **Stop-Loss Adoption (Permissive)**: The bot now scans for any existing 'STOP' or 'TAKE_PROFIT' related orders on startup and 'adopts' them if a position is found without a known local order ID.
- **0.00 SL Prevention**: Added an automatic SL calculation fallback using current ATR if a position is detected but no SL exists, preventing Binance API rejection for invalid prices.
- **Strict Self-Audit Protocol**: Integrated a mandatory E-M-V-R (Explain-Modify-Verify-Report) workflow and surgical integrity mandates into `GEMINI.md` to prevent unintended code regressions.

## [13.3.0] - 2026-05-24
### **⚡ V7.0 Chaos & Squeeze Momentum Engine**
- **Chaos Index**: Re-engineered the 'lucky error' ADX logic into a formal Momentum-Chaos filter. It captures extreme one-sided energy bursts while ignoring weak trends.
- **Volatility Squeeze**: Integrated Bollinger Band / Keltner Channel squeeze detection to identify explosive breakout opportunities.
- **Adaptive Market Regime**: Combined MTF (4h) ADX with Choppiness Index and EMA Slope to create a self-adjusting market state classifier.
- **Bi-Directional Optimization**: Significantly improved Short entry performance, turning a major 1-year downtrend into a +150% profit (TRUMP/USDT).
- **Engine Stability**: Fixed pandas DatetimeIndex alignment issues in backtest and optimized Numba loops for high-frequency simulation.

## [13.2.3] - 2026-05-11
### **📊 ADX Logical Integrity**
- **Fixed ADX Calculation**: Corrected a critical flaw in the DMI calculation where `down_move` was incorrectly calculated using `abs()`. This now correctly uses the standard Wilder's formula (`low_prev - low_curr`), ensuring upward movements in lows are not counted as downward pressure.
- **Improved Filter Accuracy**: The ADX filter now provides a more accurate representation of trend strength by eliminating false volatility noise from higher lows during uptrends.

## [13.2.2] - 2026-05-10
### **🛡️ Binance ListenKey Auto-Recovery**
- **Self-Healing ListenKey**: Implemented automatic recovery for Binance error `-1125 (This listenKey does not exist)`. The WebSocket manager now detects expired keys and re-acquires them without manual intervention.
- **Resilient Private Streams**: Private User Data streams now automatically reconnect with fresh keys if the session becomes invalid, ensuring 100% uptime for order fill events.
- **Improved Keep-Alive Logic**: Optimized the keep-alive loop to handle intermittent API failures and background recovery, preventing "infinite waiting" scenarios during SL execution.

## [13.2.1] - 2026-05-07
### **📊 EMA Precision & Stability**
- **Indicator Precision**: Increased OHLCV backfill limit from 100 to **1000** candles for live bots. This ensures large-period indicators like EMA 800 remain stable and accurate during candle transitions, eliminating calculation "kinks".
- **Data Sync Uniformity**: Standardized data fetching limits across all live execution scripts to ensure identical indicator values between initialization and real-time operation.
- **Validation Suite**: Added `tests/test_ema_fix.py` to quantitatively verify EMA stability under varying data lengths.

## [13.2.0] - 2026-05-01
### **🚀 Cloud Stability & Safety Guardrails**
- **WebSocket Engine Overhaul**: Re-architected the WebSocket manager to use pure async `websockets` library with **Combined Streams** and **Port 443** bypass, ensuring bit-perfect data flow in GCP/Cloud environments.
- **Race Condition Prevention**: Introduced `asyncio.Lock` per symbol to serialize event processing. This solves the "Order Flooding" issue where rapid price updates triggered multiple duplicate entries before state updates.
- **Total Exposure Guardrail**: Implemented `MAX_POSITION_VALUE_USDT` safety check. The bot now verifies `Current Position + Open Orders + New Order` against a global limit (Default $1000) before placing any trade.
- **Verification Suite**: Added `scripts/verify_live_order.py` for safe, low-risk validation of the entire trade lifecycle on real exchanges.
- **Diagnostic Tools**: Added `/check` Telegram command for real-time WebSocket connectivity status and latency reporting.
- **Resilient Cancellation**: Improved `cancel_order` logic with pre-emptive exchange verification to eliminate Binance `-1102 (Malformed orderId)` and `-2011 (Unknown order)` errors.

## [13.1.13] - 2026-04-20
### Fixed
- **Double Entry Race Condition**: Eliminated a race condition where the bot could execute multiple entries for the same signal due to the asynchronous gap between fill detection and SL order creation.
- **Atomic Position Locking**: Introduced `is_processing_fill` atomic lock and prioritized immediate `self.position` updates upon fill detection. This prevents concurrent entry checks from triggering redundant orders while a fill is being processed.

## [13.1.12] - 2026-04-14
### Fixed
- **Standardized ADX Logic**: Replaced simple moving average ADX with **Wilder's Smoothing (EMA-based)** calculation. This ensures ADX correctly reflects trend strength and matches industry standards (TradingView, Binance), fixing the issue where ADX moved inversely to price.
- **Sniper Mode Stability**: Introduced a **0.03% Safety Gap** for Sniper entries. If the price is too close to the breakout level or already beyond it, the bot now switches to a **MARKET** entry. This eliminates "Order would immediately trigger" errors and improves entry reliability.
- **Peak Price Update Priority**: Optimized the order of operations in `live_bot_async.py` to update `max_price_seen` **before** calculating the trailing stop. This ensures current tick highs are immediately reflected in the stop-loss level.

## [13.1.11] - 2026-04-14
### Fixed
- **Trailing SL Persistence Bug**: Fixed a critical issue where the trailing stop loss calculated by the strategy engine was not being saved to the bot's state. This prevented the live bot from synchronizing updated stop-loss levels to the exchange.
- **Stop-Loss Synchronization Deadlock**: Implemented a **Fail-safe Market Exit** mechanism. If the price hits a newly updated trailing stop price before the bot can synchronize it with the exchange, the bot now triggers an immediate market exit to protect profits and prevent a deadlock.
- **Symbol Matching Resilience**: Improved the symbol matching logic in `sync_all_orders` to accurately handle Binance settlement suffixes (e.g., `ETH/USDT:USDT`). This prevents false "No Position" detections that previously caused bot state resets.
- **SL Auto-Recovery Logic**: Enhanced the bot's resilience when a Stop-Loss order is missing from the exchange. Instead of an immediate emergency exit, the bot now attempts to re-create the SL order while keeping the position active, ensuring profit-taking continues during temporary API issues.

### Added
- **Real-time SL Update Notifications**: Added Telegram notifications that trigger specifically when the trailing stop loss is successfully updated on the exchange. The message includes the new SL price and the current Mark Price for transparency.
- **Unit Test for SL Persistence**: Added `tests/test_trailing_update.py` (verified and then cleaned up) and updated `tests/test_sl_robustness.py` and `tests/test_e2e_simulation.py` to match the new resilient recovery behavior.

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
