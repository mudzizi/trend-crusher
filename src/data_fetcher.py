import ccxt
import pandas as pd
import time
import os
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

from src.config import CONFIG
from timeseries_storage import TimeSeriesStorage

class BinanceDataFetcher:
    def __init__(self, config=CONFIG):
        self.c = config
        self.exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'enableRateLimit': True
        })

    def fetch_ohlcv(self, symbol, timeframe, since_days):
        return self.fetch_ohlcv_bundle(symbol, timeframe, since_days)["dataframe"]

    def fetch_ohlcv_bundle(self, symbol, timeframe, since_days=None, since_ms=None, limit=1500):
        if since_ms is None:
            if since_days is None:
                raise ValueError("Either since_days or since_ms must be provided.")
            since = self.exchange.parse8601((datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat())
            scope = f"last {since_days} days"
        else:
            since = since_ms
            scope = f"since {pd.to_datetime(since_ms, unit='ms', utc=True)}"
        print(f"Fetching {timeframe} data for {symbol} ({scope})...")
        all_ohlcv = []
        retries = 0
        batch_count = 0

        while since < self.exchange.milliseconds():
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since, limit=limit)
                if not ohlcv:
                    break
                since = ohlcv[-1][0] + 1
                all_ohlcv += ohlcv
                batch_count += 1
                retries = 0
                if batch_count % 50 == 0 or len(ohlcv) < limit:
                    last_seen = pd.to_datetime(ohlcv[-1][0], unit='ms', utc=True)
                    print(f"  {timeframe}: fetched {len(all_ohlcv)} rows through {last_seen}")
                if len(ohlcv) < limit:
                    break
                time.sleep(self.exchange.rateLimit / 1000)
            except Exception as e:
                retries += 1
                print(f"Error fetching {timeframe} for {symbol}: {e}")
                if retries >= 5:
                    raise
                time.sleep(min(10 * retries, 30))

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_localize(None)
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        return {
            "dataframe": df,
            "payload": {
                "exchange": "binance",
                "market_type": "future",
                "symbol": symbol,
                "timeframe": timeframe,
                "since_days": since_days,
                "since_ms": since_ms,
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "row_count": len(df),
                "ohlcv": all_ohlcv,
            },
        }

    def persist_ohlcv_snapshot(self, storage=None, symbol=None, since_days=None, as_of_time=None):
        storage = storage or TimeSeriesStorage(
            root=self.c["TIMESERIES_DIR"],
            snapshot_root=self.c["SNAPSHOT_DIR"],
            mutable_latest=self.c.get("ROLLING_TIMESERIES", False),
        )
        symbol = symbol or self.c["SYMBOL"]
        since_days = since_days or self.c["BACKTEST_DAYS"]
        as_of_time = as_of_time or datetime.now(timezone.utc)
        source = "binance_futures"
        dataset_ids = {}
        snapshot_id = self._snapshot_id(symbol) if self.c.get("ROLLING_TIMESERIES", False) else None

        for timeframe in [self.c["SIGNAL_TIMEFRAME"], self.c["TREND_TIMEFRAME"], self.c["CHECK_TIMEFRAME"]]:
            dataset_id = self._dataset_id(symbol, timeframe)
            dataset_ids[timeframe] = dataset_id
            existing_df = None
            latest_record = storage.get_latest_record("bronze", dataset_id) if self.c.get("ROLLING_TIMESERIES", False) else None
            if latest_record and Path(latest_record["path"]).exists():
                existing_df = pd.read_parquet(latest_record["path"])
                existing_df = existing_df.drop(columns=["observed_year", "observed_month"], errors="ignore")
                existing_df["timestamp"] = pd.to_datetime(existing_df["timestamp"])
                latest_timestamp = pd.to_datetime(existing_df["timestamp"].max())
                overlap_start = latest_timestamp - pd.to_timedelta(timeframe)
                since_ms = int(overlap_start.tz_localize("UTC").timestamp() * 1000)
                bundle = self.fetch_ohlcv_bundle(symbol, timeframe, since_ms=since_ms)
                df = self._merge_existing_and_new(existing_df, bundle["dataframe"])
            else:
                bundle = self.fetch_ohlcv_bundle(symbol, timeframe, since_days=since_days)
                df = bundle["dataframe"]

            if df.empty:
                raise ValueError(f"No OHLCV rows fetched for {symbol} {timeframe}")
            observed = pd.to_datetime(df["timestamp"], utc=True)
            ingested_at = datetime.now(timezone.utc)
            storage.append_raw_json(
                source=source,
                dataset_id=dataset_id,
                symbol_or_series=symbol,
                frequency=timeframe,
                payload={
                    **bundle["payload"],
                    "cumulative_row_count": len(df),
                    "incremental": existing_df is not None,
                },
                observed_at=observed.max(),
                release_time=observed.max(),
                as_of_time=as_of_time,
                ingested_at=ingested_at,
                timezone_name="UTC",
                revision_flag=False,
            )
            storage.append_parquet_dataset(
                stage="bronze",
                source=source,
                dataset_id=dataset_id,
                symbol_or_series=symbol,
                frequency=timeframe,
                frame=df,
                observed_at_column="timestamp",
                as_of_time=as_of_time,
                ingested_at=ingested_at,
                timezone_name="UTC",
                revision_flag=False,
            )

        snapshot = storage.build_snapshot(
            stage="bronze",
            requested_as_of=as_of_time,
            dataset_ids=list(dataset_ids.values()),
            snapshot_id=snapshot_id,
        )
        return snapshot, dataset_ids

    def _dataset_id(self, symbol, timeframe):
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", symbol).strip("_").lower()
        return f"ohlcv_{normalized}_{timeframe}"

    def _snapshot_id(self, symbol):
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", symbol).strip("_").lower()
        return f"bronze-{normalized}-latest"

    def _merge_existing_and_new(self, existing_df, new_df):
        merged = pd.concat([existing_df, new_df], ignore_index=True)
        merged["timestamp"] = pd.to_datetime(merged["timestamp"])
        merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        return merged

    def save_all(self):
        os.makedirs(self.c["DATA_DIR"], exist_ok=True)
        symbol = self.c["SYMBOL"]
        days = self.c["BACKTEST_DAYS"]
        
        for tf in [self.c["SIGNAL_TIMEFRAME"], self.c["TREND_TIMEFRAME"], self.c["CHECK_TIMEFRAME"]]:
            df = self.fetch_ohlcv(symbol, tf, days)
            filename = f"{self.c['DATA_DIR']}/{symbol.replace('/', '_')}_{tf}.csv"
            df.to_csv(filename, index=False)
            print(f"Saved to {filename}")

if __name__ == "__main__":
    fetcher = BinanceDataFetcher()
    fetcher.save_all()
