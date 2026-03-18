import json
from pathlib import Path

import pandas as pd

from timeseries_storage import TimeSeriesStorage


def test_snapshot_replays_revision_by_as_of(tmp_path):
    storage = TimeSeriesStorage(
        root=tmp_path / "timeseries",
        snapshot_root=tmp_path / "artifacts" / "research" / "snapshots",
    )
    payload_v1 = {"rows": [[1, 2, 3]]}
    payload_v2 = {"rows": [[4, 5, 6]]}

    storage.append_raw_json(
        source="binance_futures",
        dataset_id="ohlcv_btc_usdt_1h",
        symbol_or_series="BTC/USDT",
        frequency="1h",
        payload=payload_v1,
        observed_at="2024-01-10T00:00:00Z",
        release_time="2024-01-10T00:00:00Z",
        as_of_time="2024-01-10T00:00:00Z",
        ingested_at="2024-01-10T00:00:01Z",
    )
    storage.append_raw_json(
        source="binance_futures",
        dataset_id="ohlcv_btc_usdt_1h",
        symbol_or_series="BTC/USDT",
        frequency="1h",
        payload=payload_v2,
        observed_at="2024-02-10T00:00:00Z",
        release_time="2024-02-10T00:00:00Z",
        as_of_time="2024-02-10T00:00:00Z",
        ingested_at="2024-02-10T00:00:01Z",
        revision_flag=True,
    )

    january = storage.build_snapshot(stage="raw", requested_as_of="2024-01-31T00:00:00Z")
    february = storage.build_snapshot(stage="raw", requested_as_of="2024-02-28T00:00:00Z")

    assert len(january["entries"]) == 1
    assert len(february["entries"]) == 1
    assert january["entries"][0]["as_of_time"] == "2024-01-10T00:00:00Z"
    assert february["entries"][0]["as_of_time"] == "2024-02-10T00:00:00Z"
    assert january["entries"][0]["path"] != february["entries"][0]["path"]


def test_snapshot_uses_later_ingested_at_on_as_of_tie(tmp_path):
    storage = TimeSeriesStorage(
        root=tmp_path / "timeseries",
        snapshot_root=tmp_path / "artifacts" / "research" / "snapshots",
    )
    df_v1 = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z"],
            "close": [100.0],
        }
    )
    df_v2 = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z"],
            "close": [200.0],
        }
    )

    storage.append_parquet_dataset(
        stage="bronze",
        source="binance_futures",
        dataset_id="ohlcv_eth_usdt_1h",
        symbol_or_series="ETH/USDT",
        frequency="1h",
        frame=df_v1,
        observed_at_column="timestamp",
        as_of_time="2024-01-02T00:00:00Z",
        ingested_at="2024-01-02T00:00:01Z",
    )
    latest = storage.append_parquet_dataset(
        stage="bronze",
        source="binance_futures",
        dataset_id="ohlcv_eth_usdt_1h",
        symbol_or_series="ETH/USDT",
        frequency="1h",
        frame=df_v2,
        observed_at_column="timestamp",
        as_of_time="2024-01-02T00:00:00Z",
        ingested_at="2024-01-02T00:00:02Z",
        revision_flag=True,
    )

    snapshot = storage.build_snapshot(stage="bronze", requested_as_of="2024-01-03T00:00:00Z")

    assert snapshot["entries"][0]["path"] == latest.path
    loaded = storage.load_snapshot_dataframe(snapshot["snapshot_id"], "ohlcv_eth_usdt_1h")
    assert loaded["close"].tolist() == [200.0]


def test_partitioned_parquet_round_trip_across_months(tmp_path):
    storage = TimeSeriesStorage(
        root=tmp_path / "timeseries",
        snapshot_root=tmp_path / "artifacts" / "research" / "snapshots",
    )
    frame = pd.DataFrame(
        {
            "timestamp": ["2024-01-31T23:00:00Z", "2024-02-01T00:00:00Z"],
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
            "volume": [10.0, 20.0],
        }
    )

    record = storage.append_parquet_dataset(
        stage="bronze",
        source="binance_futures",
        dataset_id="ohlcv_sol_usdt_1h",
        symbol_or_series="SOL/USDT",
        frequency="1h",
        frame=frame,
        observed_at_column="timestamp",
        as_of_time="2024-02-02T00:00:00Z",
        ingested_at="2024-02-02T00:00:01Z",
    )
    snapshot = storage.build_snapshot(stage="bronze", requested_as_of="2024-02-03T00:00:00Z")
    loaded = storage.load_snapshot_dataframe(snapshot["snapshot_id"], "ohlcv_sol_usdt_1h")

    january_partition = Path(record.path) / "observed_year=2024" / "observed_month=01"
    february_partition = Path(record.path) / "observed_year=2024" / "observed_month=02"

    assert january_partition.exists()
    assert february_partition.exists()
    assert loaded["close"].tolist() == [1.05, 2.05]
    assert set(loaded["observed_month"].tolist()) == {"01", "02"}

    snapshot_path = Path(snapshot["path"])
    assert snapshot_path.exists()
    with snapshot_path.open("r", encoding="utf-8") as handle:
        persisted = json.load(handle)
    assert persisted["entries"][0]["dataset_id"] == "ohlcv_sol_usdt_1h"


def test_mutable_latest_keeps_single_current_record(tmp_path):
    storage = TimeSeriesStorage(
        root=tmp_path / "timeseries",
        snapshot_root=tmp_path / "artifacts" / "research" / "snapshots",
        mutable_latest=True,
    )
    frame_v1 = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z"],
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.0],
            "volume": [10.0],
        }
    )
    frame_v2 = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z"],
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.0, 2.0],
            "volume": [10.0, 20.0],
        }
    )

    storage.append_parquet_dataset(
        stage="bronze",
        source="binance_futures",
        dataset_id="ohlcv_btc_usdt_1h",
        symbol_or_series="BTC/USDT",
        frequency="1h",
        frame=frame_v1,
        observed_at_column="timestamp",
        as_of_time="2024-01-01T00:00:00Z",
        ingested_at="2024-01-01T00:00:01Z",
    )
    storage.append_parquet_dataset(
        stage="bronze",
        source="binance_futures",
        dataset_id="ohlcv_btc_usdt_1h",
        symbol_or_series="BTC/USDT",
        frequency="1h",
        frame=frame_v2,
        observed_at_column="timestamp",
        as_of_time="2024-01-02T00:00:00Z",
        ingested_at="2024-01-02T00:00:01Z",
    )

    records = storage.list_records("bronze", "ohlcv_btc_usdt_1h")
    assert len(records) == 1
    assert records[0]["as_of_time"] == "2024-01-02T00:00:00Z"
    assert "as_of=latest" in records[0]["path"]

    snapshot = storage.build_snapshot(
        stage="bronze",
        requested_as_of="2024-01-03T00:00:00Z",
        dataset_ids=["ohlcv_btc_usdt_1h"],
        snapshot_id="bronze-btc_usdt-latest",
    )
    loaded = storage.load_snapshot_dataframe(snapshot["snapshot_id"], "ohlcv_btc_usdt_1h")
    assert loaded["close"].tolist() == [1.0, 2.0]
