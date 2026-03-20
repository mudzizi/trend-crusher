import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.backtest_snapshot import calculate_mdd, load_frames_from_snapshot
from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher
from src.snapshot_store import SnapshotStore
from src.symbol_defaults import SYMBOL_DEFAULTS, apply_symbol_defaults
from src.strategy import TrendCrusherV2


def parse_csv_list(value, cast=str):
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def parse_args():
    parser = argparse.ArgumentParser(description="Tune trend timeframe and EMA period by symbol.")
    parser.add_argument("--symbols", default="TRUMP/USDT,ETH/USDT,BTC/USDT")
    parser.add_argument("--days", type=int, default=CONFIG["BACKTEST_DAYS"])
    parser.add_argument("--trend-timeframes", default="2h,4h,6h,8h,12h")
    parser.add_argument("--ema-periods", default="50,100,150,200,250,300")
    parser.add_argument("--timeseries-dir", default=CONFIG["TIMESERIES_DIR"])
    parser.add_argument("--snapshot-dir", default=CONFIG["SNAPSHOT_DIR"])
    parser.add_argument("--output-dir", default="artifacts/research")
    return parser.parse_args()


def run_backtest(df_sig, df_trend, df_check, config):
    strategy = TrendCrusherV2(config=config)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)
    final_capital = strategy.capital
    total_return = ((final_capital / config["SEED"]) - 1) * 100
    mdd = calculate_mdd(equity_curve) * 100
    trade_count = len(trades) // 2
    return total_return, mdd, trade_count, final_capital


def main():
    args = parse_args()
    symbols = parse_csv_list(args.symbols, str)
    trend_timeframes = parse_csv_list(args.trend_timeframes, str)
    ema_periods = parse_csv_list(args.ema_periods, int)
    storage = SnapshotStore(
        root=args.timeseries_dir,
        snapshot_root=args.snapshot_dir,
        mutable_latest=CONFIG["ROLLING_TIMESERIES"],
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    detail_rows = []
    summary_rows = []

    for symbol in symbols:
        base_config = apply_symbol_defaults(CONFIG, symbol)
        fetcher = BinanceDataFetcher(config=base_config)

        for trend_tf in trend_timeframes:
            trend_config = base_config.copy()
            trend_config["BACKTEST_DAYS"] = args.days
            trend_config["TIMESERIES_DIR"] = args.timeseries_dir
            trend_config["SNAPSHOT_DIR"] = args.snapshot_dir
            trend_config["TREND_TIMEFRAME"] = trend_tf
            fetcher.c = trend_config
            snapshot, _ = fetcher.persist_ohlcv_snapshot(
                storage=storage,
                symbol=symbol,
                since_days=args.days,
                as_of_time=datetime.now(timezone.utc),
            )
            df_sig, df_trend, df_check = load_frames_from_snapshot(storage, snapshot, trend_config)

            for ema_period in ema_periods:
                test_config = trend_config.copy()
                test_config["EMA_TREND_PERIOD"] = ema_period
                total_return, mdd, trade_count, final_capital = run_backtest(df_sig, df_trend, df_check, test_config)
                detail_rows.append(
                    {
                        "symbol": symbol,
                        "trend_timeframe": trend_tf,
                        "ema_period": ema_period,
                        "return_pct": round(total_return, 4),
                        "mdd_pct": round(mdd, 4),
                        "trades": trade_count,
                        "final_capital": round(final_capital, 2),
                    }
                )

        symbol_rows = [row for row in detail_rows if row["symbol"] == symbol]
        best_row = sorted(symbol_rows, key=lambda row: (-row["return_pct"], row["mdd_pct"], -row["trades"]))[0]
        defaults = SYMBOL_DEFAULTS.get(symbol.upper(), {})
        summary_rows.append(
            {
                "symbol": symbol,
                "vol_multiplier": defaults.get("VOL_MULTIPLIER"),
                "trailing_atr_mult": defaults.get("TRAILING_ATR_MULT"),
                "risk_per_trade": defaults.get("RISK_PER_TRADE"),
                "loss_cap_pct": defaults.get("MAX_TRADE_LOSS_PCT_CAP"),
                "best_trend_timeframe": best_row["trend_timeframe"],
                "best_ema_period": best_row["ema_period"],
                "return_pct": best_row["return_pct"],
                "mdd_pct": best_row["mdd_pct"],
                "trades": best_row["trades"],
                "final_capital": best_row["final_capital"],
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = output_dir / f"trend_ma_tuning_detail_{timestamp}.csv"
    summary_path = output_dir / f"trend_ma_tuning_summary_{timestamp}.csv"

    detail_df = pd.DataFrame(detail_rows).sort_values(["symbol", "return_pct", "mdd_pct"], ascending=[True, False, True])
    summary_df = pd.DataFrame(summary_rows).sort_values("symbol")
    detail_df.to_csv(detail_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    print("\n[Trend MA Tuning Summary]")
    print(summary_df.to_string(index=False))
    print(f"\nDetail CSV: {detail_path}")
    print(f"Summary CSV: {summary_path}")


if __name__ == "__main__":
    main()
