# Changelog

All notable changes to the TrendCrusher project will be documented in this file.

## [v11.0.0] - 2026-03-21 (Current)
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
