import argparse

import numpy as np
import pandas as pd

from src.config import CONFIG
from src.data_fetcher import BinanceDataFetcher
from src.indicators import calculate_donchian, calculate_ema
from src.strategy import TrendCrusherV2
from src.visualizer import TradingVisualizer
from timeseries_storage import TimeSeriesStorage


def calculate_mdd(equity_curve):
    if not equity_curve:
        return 0
    curve = np.array(equity_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (peak - curve) / (peak + 1e-10)
    return np.max(drawdown)


def parse_args():
    parser = argparse.ArgumentParser(description="Run a snapshot-backed TrendCrusher backtest.")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"])
    parser.add_argument("--days", type=int, default=CONFIG["BACKTEST_DAYS"])
    parser.add_argument("--as-of", dest="as_of", default=None, help="UTC timestamp, e.g. 2026-03-18T12:00:00Z")
    parser.add_argument("--snapshot-id", default=None, help="Reuse an existing bronze snapshot instead of fetching new data.")
    parser.add_argument("--cap-loss-pct", type=float, default=None, help="Cap per-trade capital loss to this percentage.")
    parser.add_argument("--vol-multiplier", type=float, default=None)
    parser.add_argument("--trailing-atr-mult", type=float, default=None)
    parser.add_argument("--risk-per-trade", type=float, default=None)
    parser.add_argument("--ema-period", type=int, default=None)
    parser.add_argument("--timeseries-dir", default=CONFIG["TIMESERIES_DIR"])
    parser.add_argument("--snapshot-dir", default=CONFIG["SNAPSHOT_DIR"])
    return parser.parse_args()


def completed_trades(trades):
    results = []
    for index in range(0, len(trades), 2):
        if index + 1 >= len(trades):
            break
        opened = trades[index]
        closed = trades[index + 1]
        raw_pnl_pct = ((closed["price"] / opened["price"]) - 1) * 100
        pnl_pct = raw_pnl_pct if opened["side"] == "LONG" else -raw_pnl_pct
        results.append(
            {
                "open_time": opened["time"],
                "close_time": closed["time"],
                "side": opened["side"],
                "open_price": opened["price"],
                "close_price": closed["price"],
                "pnl_pct": pnl_pct,
                "cap_applied": closed.get("cap_applied", False),
            }
        )
    return results


def equity_frame(df_sig, equity_curve):
    start_index = max(CONFIG["DONCHIAN_PERIOD"], 1)
    timestamps = df_sig["timestamp"].iloc[start_index : start_index + len(equity_curve)].reset_index(drop=True)
    if len(timestamps) < len(equity_curve):
        padding = pd.Series([df_sig["timestamp"].iloc[-1]] * (len(equity_curve) - len(timestamps)))
        timestamps = pd.concat([timestamps, padding], ignore_index=True)
    return pd.DataFrame({"timestamp": timestamps, "balance": equity_curve})


def load_frames_from_snapshot(storage, snapshot, config):
    dataset_ids = {entry["frequency"]: entry["dataset_id"] for entry in snapshot["entries"]}
    df_sig = storage.load_snapshot_dataframe(snapshot["snapshot_id"], dataset_ids[config["SIGNAL_TIMEFRAME"]]).sort_values("timestamp")
    df_trend = storage.load_snapshot_dataframe(snapshot["snapshot_id"], dataset_ids[config["TREND_TIMEFRAME"]]).sort_values("timestamp")
    df_check = storage.load_snapshot_dataframe(snapshot["snapshot_id"], dataset_ids[config["CHECK_TIMEFRAME"]]).sort_values("timestamp")
    if config["BACKTEST_DAYS"]:
        end_time = pd.to_datetime(df_sig["timestamp"]).max()
        cutoff = end_time - pd.Timedelta(days=config["BACKTEST_DAYS"])
        df_sig = df_sig[pd.to_datetime(df_sig["timestamp"]) >= cutoff].reset_index(drop=True)
        df_trend = df_trend[pd.to_datetime(df_trend["timestamp"]) >= cutoff].reset_index(drop=True)
        df_check = df_check[pd.to_datetime(df_check["timestamp"]) >= cutoff].reset_index(drop=True)
    return df_sig, df_trend, df_check


def add_report_indicators(df_sig, df_trend, config):
    report_df = df_sig.copy()
    report_df["upper"], report_df["lower"] = calculate_donchian(report_df, period=config["DONCHIAN_PERIOD"])
    ema_series = calculate_ema(df_trend, period=config["EMA_TREND_PERIOD"])
    ema_frame = pd.DataFrame({"timestamp": pd.to_datetime(df_trend["timestamp"]), "ema_h": ema_series})
    report_df = report_df.copy()
    report_df["timestamp"] = pd.to_datetime(report_df["timestamp"])
    report_df = report_df.merge(ema_frame, on="timestamp", how="left")
    report_df["ema_h"] = report_df["ema_h"].ffill()
    return report_df


def main():
    args = parse_args()
    config = CONFIG.copy()
    config["SYMBOL"] = args.symbol
    config["BACKTEST_DAYS"] = args.days
    config["TIMESERIES_DIR"] = args.timeseries_dir
    config["SNAPSHOT_DIR"] = args.snapshot_dir
    config["MAX_TRADE_LOSS_PCT_CAP"] = args.cap_loss_pct
    if args.vol_multiplier is not None:
        config["VOL_MULTIPLIER"] = args.vol_multiplier
    if args.trailing_atr_mult is not None:
        config["TRAILING_ATR_MULT"] = args.trailing_atr_mult
    if args.risk_per_trade is not None:
        config["RISK_PER_TRADE"] = args.risk_per_trade
    if args.ema_period is not None:
        config["EMA_TREND_PERIOD"] = args.ema_period

    storage = TimeSeriesStorage(
        root=config["TIMESERIES_DIR"],
        snapshot_root=config["SNAPSHOT_DIR"],
        mutable_latest=config["ROLLING_TIMESERIES"],
    )
    if args.snapshot_id:
        snapshot = storage.read_snapshot(args.snapshot_id)
    else:
        requested_as_of = pd.Timestamp(args.as_of, tz="UTC") if args.as_of else pd.Timestamp.utcnow()
        fetcher = BinanceDataFetcher(config=config)
        snapshot, _ = fetcher.persist_ohlcv_snapshot(
            storage=storage,
            symbol=config["SYMBOL"],
            since_days=config["BACKTEST_DAYS"],
            as_of_time=requested_as_of.to_pydatetime(),
        )

    df_sig, df_trend, df_check = load_frames_from_snapshot(storage, snapshot, config)

    strategy = TrendCrusherV2(config=config)
    trades, equity_curve = strategy.run_precision_backtest(df_sig, df_trend, df_check)

    print("\n" + "=" * 80)
    print("[TrendCrusher] Snapshot Backtest Report")
    print("=" * 80)
    print(f"Symbol: {config['SYMBOL']}")
    print(f"As-Of: {snapshot['requested_as_of']}")
    print(f"Snapshot ID: {snapshot['snapshot_id']}")
    print(f"Snapshot Path: {snapshot['path']}")
    print(f"Timeseries Root: {storage.root}")
    print(
        "Params: "
        f"Vol={config['VOL_MULTIPLIER']}, "
        f"Trail={config['TRAILING_ATR_MULT']}, "
        f"Risk={config['RISK_PER_TRADE']}, "
        f"EMA={config['EMA_TREND_PERIOD']}"
    )
    if config["MAX_TRADE_LOSS_PCT_CAP"] is not None:
        print(f"Loss Cap: -{config['MAX_TRADE_LOSS_PCT_CAP']:.2f}% per trade")

    if not trades:
        print("No trades executed.")
        print("=" * 80)
        return

    trades_summary = completed_trades(trades)
    final_capital = strategy.capital
    total_return = ((final_capital / config["SEED"]) - 1) * 100
    max_drawdown = calculate_mdd(equity_curve) * 100
    report_df = add_report_indicators(df_sig, df_trend, config)
    trades_df = pd.DataFrame(trades_summary)
    equity_df = equity_frame(df_sig, equity_curve)
    report_path = TradingVisualizer(report_dir="reports").generate_report(report_df, trades_df, equity_df, config["SYMBOL"])

    print(f"Total Return: {total_return:+.2f}%")
    print(f"Max Drawdown: {max_drawdown:.2f}%")
    print(f"Trades: {len(trades_summary)}")
    print(f"Final Capital: {final_capital:,.2f} USDT")
    print(f"Report Saved: {report_path}")
    print("-" * 80)
    print(f"{'Open Time':<20} | {'Close Time':<20} | {'Side':<6} | {'PnL (%)'}")
    print("-" * 80)
    for trade in trades_summary[-10:]:
        print(
            f"{str(trade['open_time']):<20} | "
            f"{str(trade['close_time']):<20} | "
            f"{trade['side']:<6} | "
            f"{trade['pnl_pct']:+.2f}%"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
