from __future__ import annotations

import hashlib
import json
import sqlite3
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


STAGES = ("raw", "bronze", "silver", "gold")


@dataclass(frozen=True)
class ManifestRecord:
    stage: str
    source: str
    dataset_id: str
    symbol_or_series: str
    frequency: str
    observed_at: str
    release_time: str
    ingested_at: str
    as_of_time: str
    revision_flag: bool
    timezone: str
    hash: str
    path: str
    format: str
    observed_from: str | None = None
    observed_to: str | None = None
    row_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | pd.Timestamp | str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            value = value.tz_localize("UTC")
        value = value.to_pydatetime()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _path_stamp(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace(".", "").replace("+0000", "Z").replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_directory(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(str(child.relative_to(path)).encode("utf-8"))
        with child.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


class TimeSeriesStorage:
    def __init__(
        self,
        root: str | Path = "timeseries",
        snapshot_root: str | Path = "artifacts/research/snapshots",
        mutable_latest: bool = False,
    ):
        self.root = Path(root).resolve()
        self.snapshot_root = Path(snapshot_root).resolve()
        self.mutable_latest = mutable_latest
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        for stage in STAGES:
            self._ensure_stage(stage)

    def append_raw_json(
        self,
        *,
        source: str,
        dataset_id: str,
        symbol_or_series: str,
        frequency: str,
        payload: dict[str, Any],
        observed_at: datetime | pd.Timestamp | str,
        release_time: datetime | pd.Timestamp | str,
        as_of_time: datetime | pd.Timestamp | str,
        ingested_at: datetime | pd.Timestamp | str | None = None,
        timezone_name: str = "UTC",
        revision_flag: bool = False,
    ) -> ManifestRecord:
        ingested_at = ingested_at or _utc_now()
        record_path = self._raw_record_path(source, dataset_id, as_of_time, ingested_at)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        if self.mutable_latest and record_path.exists():
            record_path.unlink()
        with record_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))

        record = ManifestRecord(
            stage="raw",
            source=source,
            dataset_id=dataset_id,
            symbol_or_series=symbol_or_series,
            frequency=frequency,
            observed_at=_isoformat(observed_at),
            release_time=_isoformat(release_time),
            ingested_at=_isoformat(ingested_at),
            as_of_time=_isoformat(as_of_time),
            revision_flag=revision_flag,
            timezone=timezone_name,
            hash=_hash_file(record_path),
            path=str(record_path),
            format="json",
        )
        self._append_manifest_record(record)
        return record

    def append_parquet_dataset(
        self,
        *,
        stage: str,
        source: str,
        dataset_id: str,
        symbol_or_series: str,
        frequency: str,
        frame: pd.DataFrame,
        observed_at_column: str,
        as_of_time: datetime | pd.Timestamp | str,
        ingested_at: datetime | pd.Timestamp | str | None = None,
        timezone_name: str = "UTC",
        revision_flag: bool = False,
    ) -> ManifestRecord:
        if stage not in STAGES:
            raise ValueError(f"Unsupported stage: {stage}")
        if stage == "raw":
            raise ValueError("Use append_raw_json for raw stage payloads.")

        ingested_at = ingested_at or _utc_now()
        dataset_root = self._dataset_root(stage, source, dataset_id, as_of_time, ingested_at)
        df = frame.copy()
        observed = pd.to_datetime(df[observed_at_column], utc=True)
        df[observed_at_column] = observed.dt.tz_localize(None)
        df["observed_year"] = observed.dt.strftime("%Y")
        df["observed_month"] = observed.dt.strftime("%m")
        if self.mutable_latest and dataset_root.exists():
            shutil.rmtree(dataset_root)
        df.to_parquet(dataset_root, index=False, partition_cols=["observed_year", "observed_month"])

        record = ManifestRecord(
            stage=stage,
            source=source,
            dataset_id=dataset_id,
            symbol_or_series=symbol_or_series,
            frequency=frequency,
            observed_at=_isoformat(observed.max()),
            release_time=_isoformat(observed.max()),
            ingested_at=_isoformat(ingested_at),
            as_of_time=_isoformat(as_of_time),
            revision_flag=revision_flag,
            timezone=timezone_name,
            hash=_hash_directory(dataset_root),
            path=str(dataset_root),
            format="parquet_dataset",
            observed_from=_isoformat(observed.min()),
            observed_to=_isoformat(observed.max()),
            row_count=int(len(df)),
        )
        self._append_manifest_record(record)
        return record

    def build_snapshot(
        self,
        *,
        stage: str,
        requested_as_of: datetime | pd.Timestamp | str,
        dataset_ids: list[str] | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        if stage not in STAGES:
            raise ValueError(f"Unsupported stage: {stage}")
        requested_as_of_str = _isoformat(requested_as_of)
        snapshot_id = snapshot_id or f"{stage}-{_path_stamp(requested_as_of_str)}"

        query = """
            SELECT * FROM manifest_records
            WHERE as_of_time <= ?
        """
        params: list[Any] = [requested_as_of_str]
        if dataset_ids:
            placeholders = ",".join("?" for _ in dataset_ids)
            query += f" AND dataset_id IN ({placeholders})"
            params.extend(dataset_ids)
        query += " ORDER BY dataset_id ASC, as_of_time DESC, ingested_at DESC, id DESC"

        selected: dict[str, dict[str, Any]] = {}
        with self._connect(stage) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(query, params).fetchall():
                record = dict(row)
                record["revision_flag"] = bool(record["revision_flag"])
                if record["dataset_id"] not in selected:
                    selected[record["dataset_id"]] = record

        snapshot = {
            "snapshot_id": snapshot_id,
            "stage": stage,
            "requested_as_of": requested_as_of_str,
            "created_at": _isoformat(_utc_now()),
            "entries": list(selected.values()),
        }
        snapshot_path = self.snapshot_root / f"{snapshot_id}.json"
        with snapshot_path.open("w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=True, indent=2, sort_keys=True)
        snapshot["path"] = str(snapshot_path)
        return snapshot

    def read_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        snapshot_path = self.snapshot_root / f"{snapshot_id}.json"
        with snapshot_path.open("r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
        snapshot["path"] = str(snapshot_path)
        return snapshot

    def load_snapshot_dataframe(self, snapshot_id: str, dataset_id: str) -> pd.DataFrame:
        snapshot = self.read_snapshot(snapshot_id)
        for entry in snapshot["entries"]:
            if entry["dataset_id"] != dataset_id:
                continue
            if entry["format"] != "parquet_dataset":
                raise ValueError(f"Dataset {dataset_id} is not stored as a parquet dataset.")
            frame = pd.read_parquet(entry["path"])
            if "observed_year" in frame:
                frame["observed_year"] = frame["observed_year"].astype(str).str.zfill(4)
            if "observed_month" in frame:
                frame["observed_month"] = frame["observed_month"].astype(str).str.zfill(2)
            return frame
        raise KeyError(f"Dataset {dataset_id} not found in snapshot {snapshot_id}.")

    def get_latest_record(self, stage: str, dataset_id: str) -> dict[str, Any] | None:
        with self._connect(stage) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM manifest_records
                WHERE dataset_id = ?
                ORDER BY as_of_time DESC, ingested_at DESC, id DESC
                LIMIT 1
                """,
                (dataset_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["revision_flag"] = bool(record["revision_flag"])
        return record

    def list_records(self, stage: str, dataset_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM manifest_records"
        params: list[Any] = []
        if dataset_id:
            query += " WHERE dataset_id = ?"
            params.append(dataset_id)
        query += " ORDER BY id ASC"
        with self._connect(stage) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["revision_flag"] = bool(record["revision_flag"])
            records.append(record)
        return records

    def _ensure_stage(self, stage: str) -> None:
        stage_root = self.root / stage
        stage_root.mkdir(parents=True, exist_ok=True)
        manifest_jsonl = stage_root / "manifest.jsonl"
        manifest_sqlite = stage_root / "manifest.sqlite3"
        if not manifest_jsonl.exists():
            manifest_jsonl.touch()
        with sqlite3.connect(manifest_sqlite) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manifest_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stage TEXT NOT NULL,
                    source TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    symbol_or_series TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    release_time TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    as_of_time TEXT NOT NULL,
                    revision_flag INTEGER NOT NULL,
                    timezone TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    path TEXT NOT NULL,
                    format TEXT NOT NULL,
                    observed_from TEXT,
                    observed_to TEXT,
                    row_count INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_manifest_dataset_version
                ON manifest_records (dataset_id, as_of_time, ingested_at)
                """
            )

    def _append_manifest_record(self, record: ManifestRecord) -> None:
        stage_root = self.root / record.stage
        manifest_jsonl = stage_root / "manifest.jsonl"
        with self._connect(record.stage) as conn:
            if self.mutable_latest:
                conn.execute(
                    """
                    DELETE FROM manifest_records
                    WHERE source = ? AND dataset_id = ?
                    """,
                    (record.source, record.dataset_id),
                )
            conn.execute(
                """
                INSERT INTO manifest_records (
                    stage, source, dataset_id, symbol_or_series, frequency,
                    observed_at, release_time, ingested_at, as_of_time,
                    revision_flag, timezone, hash, path, format,
                    observed_from, observed_to, row_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.stage,
                    record.source,
                    record.dataset_id,
                    record.symbol_or_series,
                    record.frequency,
                    record.observed_at,
                    record.release_time,
                    record.ingested_at,
                    record.as_of_time,
                    int(record.revision_flag),
                    record.timezone,
                    record.hash,
                    record.path,
                    record.format,
                    record.observed_from,
                    record.observed_to,
                    record.row_count,
                ),
            )
        if self.mutable_latest:
            self._rewrite_manifest_jsonl(record.stage)
        else:
            with manifest_jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=True, sort_keys=True) + "\n")

    def _rewrite_manifest_jsonl(self, stage: str) -> None:
        manifest_jsonl = self.root / stage / "manifest.jsonl"
        records = self.list_records(stage)
        with manifest_jsonl.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

    def _raw_record_path(
        self,
        source: str,
        dataset_id: str,
        as_of_time: datetime | pd.Timestamp | str,
        ingested_at: datetime | pd.Timestamp | str,
    ) -> Path:
        if self.mutable_latest:
            return (
                self.root
                / "raw"
                / source
                / dataset_id
                / "as_of=latest"
                / "ingested_at=current.json"
            )
        return (
            self.root
            / "raw"
            / source
            / dataset_id
            / f"as_of={_path_stamp(_isoformat(as_of_time))}"
            / f"ingested_at={_path_stamp(_isoformat(ingested_at))}.json"
        )

    def _dataset_root(
        self,
        stage: str,
        source: str,
        dataset_id: str,
        as_of_time: datetime | pd.Timestamp | str,
        ingested_at: datetime | pd.Timestamp | str,
    ) -> Path:
        if self.mutable_latest:
            return (
                self.root
                / stage
                / source
                / dataset_id
                / "as_of=latest"
                / "ingested_at=current"
            )
        return (
            self.root
            / stage
            / source
            / dataset_id
            / f"as_of={_path_stamp(_isoformat(as_of_time))}"
            / f"ingested_at={_path_stamp(_isoformat(ingested_at))}"
        )

    def _connect(self, stage: str) -> sqlite3.Connection:
        return sqlite3.connect(self.root / stage / "manifest.sqlite3")
