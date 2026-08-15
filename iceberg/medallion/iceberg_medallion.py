from __future__ import annotations

import os
import sys
import time
import json
import math
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
from pyarrow.fs import FileSelector, S3FileSystem
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.expressions import In
from pyiceberg.exceptions import NoSuchTableError
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from common.ops import Metrics
from common.cutover import validate_runtime_config
from b2_spike import collapse_delta, resolve_against_current

CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://iceberg-rest:8181")
WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "de-practicum")

BRONZE_NAMESPACE = os.getenv("BRONZE_NAMESPACE", "bronze")
BRONZE_TABLE = os.getenv("BRONZE_TABLE", "orders")
SILVER_NAMESPACE = os.getenv("SILVER_NAMESPACE", "silver")
SILVER_TABLE = os.getenv("SILVER_TABLE", "orders_clean")
GOLD_NAMESPACE = os.getenv("GOLD_NAMESPACE", "gold")
GOLD_TABLE = os.getenv("GOLD_TABLE", "orders_daily_metrics")

INTERVAL = int(os.getenv("MEDALLION_INTERVAL_SECONDS", "60"))
SILVER_MODE = os.getenv("SILVER_MODE", "legacy").lower()
GOLD_SOURCE = os.getenv("GOLD_SOURCE", "legacy").lower()
SHADOW_COMPARE_ENABLED = os.getenv("SHADOW_COMPARE", "0") == "1"
BRONZE_OUTBOX_PREFIX = os.getenv("BRONZE_OUTBOX_PREFIX", "streaming/bronze_outbox")
MEDALLION_PROGRESS_PATH = os.getenv(
    "MEDALLION_PROGRESS_PATH", "streaming/medallion/progress.json"
)
MEDALLION_COMPLETION_LEDGER_PREFIX = os.getenv(
    "MEDALLION_COMPLETION_LEDGER_PREFIX",
    "streaming/medallion/completion-ledger",
)
MAX_COMPLETED_PROGRESS = int(os.getenv("MAX_COMPLETED_PROGRESS", "100"))
SIMULATE_B2_CRASH_BEFORE_COMMIT = (
    os.getenv("SIMULATE_B2_CRASH_BEFORE_COMMIT", "0") == "1"
)
SIMULATE_B2_CRASH_AFTER_COMMIT = os.getenv("SIMULATE_B2_CRASH_AFTER_COMMIT", "0") == "1"

SILVER_WORK_ID_KEY = "silver-work-id"
PROGRESS_VERSION = 1

RUNTIME_CONFIG = {
    "SILVER_MODE": SILVER_MODE,
    "GOLD_SOURCE": GOLD_SOURCE,
    "SHADOW_COMPARE": "1" if SHADOW_COMPARE_ENABLED else "0",
}

VALID_STATUSES = [
    s.strip()
    for s in os.getenv(
        "QUALITY_VALID_STATUSES", "created,paid,shipped,delivered"
    ).split(",")
    if s.strip()
]
FAIL_ON_VIOLATIONS = os.getenv("QUALITY_FAIL_ON_VIOLATIONS", "0") == "1"

SILVER_SCHEMA = Schema(
    NestedField(1, "order_id", StringType(), required=False),
    NestedField(2, "customer", StringType(), required=False),
    NestedField(3, "amount", DoubleType(), required=False),
    NestedField(4, "country", StringType(), required=False),
    NestedField(5, "status", StringType(), required=False),
    NestedField(6, "event_time", TimestampType(), required=False),
    NestedField(7, "kafka_timestamp", TimestampType(), required=False),
    NestedField(8, "kafka_partition", IntegerType(), required=False),
    NestedField(9, "kafka_offset", LongType(), required=False),
    NestedField(10, "event_date", DateType(), required=False),
    NestedField(11, "business_version", LongType(), required=False),
)

SILVER_PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=10,
        field_id=1000,
        transform=DayTransform(),
        name="event_date_day",
    )
)

GOLD_SCHEMA = Schema(
    NestedField(1, "event_date", DateType(), required=False),
    NestedField(2, "country", StringType(), required=False),
    NestedField(3, "status", StringType(), required=False),
    NestedField(4, "orders_count", LongType(), required=False),
    NestedField(5, "total_amount", DoubleType(), required=False),
    NestedField(6, "avg_amount", DoubleType(), required=False),
    NestedField(7, "distinct_customers", LongType(), required=False),
)


def get_catalog() -> RestCatalog:
    return RestCatalog(
        "default",
        **{
            "uri": CATALOG_URI,
            "warehouse": WAREHOUSE,
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": S3_REGION,
            "s3.path-style-access": "true",
        },
    )


def get_fs() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region=S3_REGION,
        scheme="http",
    )


def _storage_path(path: str) -> str:
    parsed = urlparse(path)
    if parsed.scheme in {"s3", "s3a", "s3n"}:
        return f"{parsed.netloc}/{parsed.path.lstrip('/')}"
    if parsed.scheme:
        raise ValueError(f"Unsupported storage path scheme: {parsed.scheme}")
    if path.startswith(f"{MINIO_BUCKET}/"):
        return path
    return f"{MINIO_BUCKET}/{path.lstrip('/')}"


def _outbox_base_path() -> str:
    return _storage_path(BRONZE_OUTBOX_PREFIX)


def _progress_path() -> str:
    return _storage_path(MEDALLION_PROGRESS_PATH)


def _read_json(fs: S3FileSystem, path: str) -> dict:
    with fs.open_input_file(path) as source:
        return json.loads(source.read().decode("utf-8"))


def list_bronze_work(fs: S3FileSystem) -> list[dict]:
    """Read committed Bronze work manifests published by the writer."""

    selector = FileSelector(
        base_dir=_outbox_base_path(),
        recursive=True,
        allow_not_found=True,
    )
    records = []
    for info in sorted(fs.get_file_info(selector), key=lambda item: item.path):
        if not info.is_file or not info.path.endswith(".json"):
            continue
        record = _read_json(fs, info.path)
        if record.get("version") != 1 or not record.get("load_id"):
            raise ValueError(f"Invalid Bronze outbox record: {info.path}")
        record["_object_path"] = info.path
        record["source_paths"] = list(record.get("source_paths", []))
        record["bronze_data_files"] = list(record.get("bronze_data_files", []))
        records.append(record)
    return records


def load_progress(fs: S3FileSystem) -> dict:
    try:
        progress = _read_json(fs, _progress_path())
    except (FileNotFoundError, OSError):
        progress = {}
    progress.setdefault("version", PROGRESS_VERSION)
    progress.setdefault("next_sequence", 0)
    progress.setdefault("work", {})
    progress.setdefault("completed", {})
    return progress


def save_progress(fs: S3FileSystem, progress: dict) -> None:
    raw = json.dumps(progress, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with fs.open_output_stream(_progress_path()) as output:
        output.write(raw)


def _completion_ledger_base_path() -> str:
    return f"{MINIO_BUCKET}/{MEDALLION_COMPLETION_LEDGER_PREFIX}".rstrip("/")


def _completion_receipt_path(load_id: str) -> str:
    if not load_id or "/" in load_id:
        raise ValueError(f"Invalid completion manifest identity: {load_id!r}")
    return f"{_completion_ledger_base_path()}/{load_id}.json"


def load_completion_ledger(fs: S3FileSystem) -> dict[str, dict]:
    """Load immutable per-manifest completion receipts from durable storage."""

    selector = FileSelector(
        base_dir=_completion_ledger_base_path(),
        recursive=False,
        allow_not_found=True,
    )
    receipts: dict[str, dict] = {}
    for info in sorted(fs.get_file_info(selector), key=lambda item: item.path):
        if not info.is_file or not info.path.endswith(".json"):
            continue
        receipt = _read_json(fs, info.path)
        load_id = str(receipt.get("load_id", ""))
        if receipt.get("result") != "success" or not load_id:
            raise ValueError(f"Invalid completion receipt: {info.path}")
        if load_id in receipts and receipts[load_id] != receipt:
            raise ValueError(f"Ambiguous completion receipts for {load_id}")
        receipts[load_id] = receipt
    return receipts


def _append_completion_receipt(
    fs: S3FileSystem,
    record: dict,
    *,
    sequence: int,
    snapshot_id: int | None,
    changed_keys: list[str],
    source_epoch_id: str | None,
    output_digest: str | None,
) -> dict:
    """Write one immutable success receipt after the Silver commit."""

    load_id = str(record["load_id"])
    path = _completion_receipt_path(load_id)
    try:
        existing = _read_json(fs, path)
    except (FileNotFoundError, OSError):
        existing = None
    if existing is not None:
        if (
            str(existing.get("load_id")) != load_id
            or existing.get("manifest_id") != record.get("_object_path")
            or existing.get("result") != "success"
        ):
            raise ValueError(f"Ambiguous completion identity for {load_id}")
        return existing

    receipt = {
        "manifest_id": record.get("_object_path", _completion_receipt_path(load_id)),
        "load_id": load_id,
        "sequence": sequence,
        "source_paths": sorted(record.get("source_paths", [])),
        "source_epoch_id": source_epoch_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "result": "success",
        "silver_snapshot_id": snapshot_id,
        "changed_keys": sorted(changed_keys),
        "output_digest": output_digest,
    }
    with fs.open_output_stream(path) as output:
        output.write(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        )
    return receipt


def _rows_output_digest(rows: list[dict]) -> str:
    canonical = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_epoch_id(rows: list[dict]) -> str | None:
    epochs = sorted(
        {str(row["source_epoch_id"]) for row in rows if row.get("source_epoch_id")}
    )
    return epochs[0] if len(epochs) == 1 else None


def delete_bronze_work(fs: S3FileSystem, record: dict) -> None:
    fs.delete_file(record["_object_path"])


def silver_committed_work_ids(silver) -> dict[str, int]:
    committed: dict[str, int] = {}
    for snapshot in silver.metadata.snapshots:
        if not snapshot.summary:
            continue
        work_id = snapshot.summary.additional_properties.get(SILVER_WORK_ID_KEY)
        if work_id:
            committed[work_id] = snapshot.snapshot_id
    return committed


def _prune_completed(progress: dict) -> None:
    completed = progress["completed"]
    while len(completed) > MAX_COMPLETED_PROGRESS:
        oldest = min(
            completed,
            key=lambda load_id: completed[load_id].get("sequence", 0),
        )
        del completed[oldest]


def _mark_b2_completed(
    fs: S3FileSystem,
    progress: dict,
    record: dict,
    snapshot_id: int | None,
    changed_keys: list[str],
    *,
    delete_outbox: bool = True,
    source_epoch_id: str | None = None,
    output_digest: str | None = None,
) -> None:
    load_id = record["load_id"]
    next_sequence = progress["next_sequence"] + 1
    completion = _append_completion_receipt(
        fs,
        record,
        sequence=next_sequence,
        snapshot_id=snapshot_id,
        changed_keys=changed_keys,
        source_epoch_id=source_epoch_id,
        output_digest=output_digest,
    )
    progress["next_sequence"] = max(
        progress["next_sequence"], int(completion.get("sequence", next_sequence))
    )
    progress["completed"][load_id] = {
        "sequence": completion.get("sequence", next_sequence),
        "silver_snapshot_id": completion.get("silver_snapshot_id", snapshot_id),
        "changed_keys": sorted(changed_keys),
    }
    progress["work"].pop(load_id, None)
    _prune_completed(progress)
    # This is the durable progress commit.  Normal processing cleans the
    # outbox only after this commit.  Recovery reconciliation may deliberately
    # leave the manifest in place for a separately approved handoff cleanup.
    save_progress(fs, progress)
    if delete_outbox:
        delete_bronze_work(fs, record)


def _reserve_b2_work(fs: S3FileSystem, progress: dict, record: dict) -> None:
    progress["work"][record["load_id"]] = {
        "status": "in_flight",
        "source_paths": sorted(record["source_paths"]),
        "bronze_data_files": sorted(record["bronze_data_files"]),
    }
    save_progress(fs, progress)


def read_bronze_work(fs: S3FileSystem, bronze, record: dict) -> pa.Table:
    paths = record["bronze_data_files"]
    if not paths:
        # Recovery from a legacy/manual manifest remains safe, but uses the
        # full Bronze scan because no file-level provenance is available.
        return bronze.scan().to_arrow()
    dataset = ds.dataset(
        [_storage_path(path) for path in paths],
        format="parquet",
        filesystem=fs,
    )
    arrow_table = dataset.to_table()
    target_types = [
        pa.timestamp("us", tz=None) if pa.types.is_timestamp(field.type) else field.type
        for field in arrow_table.schema
    ]
    return arrow_table.cast(
        pa.schema(
            [
                (field.name, target_type)
                for field, target_type in zip(
                    arrow_table.schema, target_types, strict=True
                )
            ]
        )
    )


def _rows_to_silver(rows: list[dict]) -> pa.Table:
    columns = [
        "order_id",
        "customer",
        "amount",
        "country",
        "status",
        "event_time",
        "kafka_timestamp",
        "kafka_partition",
        "kafka_offset",
        "event_date",
        "business_version",
    ]
    return pa.table(
        {
            name: pa.array([row.get(name) for row in rows], type=_SILVER_TYPES[name])
            for name in columns
        }
    )


def _planned_scan_cost(scan) -> tuple[int, int]:
    tasks = list(scan.plan_files())
    return len(tasks), sum(task.file.file_size_in_bytes for task in tasks)


def _snapshot_write_cost(snapshot) -> tuple[int, int, int, int]:
    if snapshot is None or snapshot.summary is None:
        return 0, 0, 0, 0
    properties = snapshot.summary.additional_properties
    return (
        int(properties.get("deleted-data-files", 0)),
        int(properties.get("added-data-files", 0)),
        int(properties.get("removed-files-size", 0)),
        int(properties.get("added-files-size", 0)),
    )


def run_b2(
    catalog: RestCatalog, metrics: Metrics, fs: S3FileSystem | None = None
) -> None:
    """Process committed Bronze outbox work with the B2 Silver projection."""

    fs = fs or get_fs()
    bronze_id = f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}"
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    try:
        bronze = catalog.load_table(bronze_id)
    except NoSuchTableError:
        print("Bronze table not available yet; skipping B2 cycle", flush=True)
        return

    ensure_table(catalog, silver_id, SILVER_SCHEMA, SILVER_PARTITION_SPEC)
    silver = catalog.load_table(silver_id)
    progress = load_progress(fs)
    records = list_bronze_work(fs)
    completion_ledger = load_completion_ledger(fs)

    # A completed marker is durable independently of Silver snapshot history.
    # It also makes a stale duplicate outbox object harmless.
    for record in records:
        if record["load_id"] in progress["completed"]:
            delete_bronze_work(fs, record)

    committed_ids = silver_committed_work_ids(silver)
    processed = 0
    keys_processed = 0
    lower_versions_ignored = 0
    ff14_conflicts = 0
    files_processed = 0
    files_planned = 0
    bytes_planned = 0
    files_removed = 0
    files_added = 0
    bytes_removed = 0
    bytes_added = 0
    snapshot_delta = 0
    started = time.monotonic()
    for record in records:
        load_id = record["load_id"]
        if load_id in progress["completed"]:
            continue
        if load_id in completion_ledger:
            receipt = completion_ledger[load_id]
            _mark_b2_completed(
                fs,
                progress,
                record,
                receipt.get("silver_snapshot_id"),
                receipt.get("changed_keys", []),
                source_epoch_id=receipt.get("source_epoch_id"),
                output_digest=receipt.get("output_digest"),
            )
            processed += 1
            files_processed += len(record["bronze_data_files"])
            continue
        if load_id in progress["work"] and load_id in committed_ids:
            _mark_b2_completed(
                fs,
                progress,
                record,
                committed_ids[load_id],
                progress["work"][load_id].get("changed_keys", []),
            )
            processed += 1
            files_processed += len(record["bronze_data_files"])
            continue
        if load_id not in progress["work"]:
            _reserve_b2_work(fs, progress, record)

        delta = read_bronze_work(fs, bronze, record)
        incoming = delta.to_pylist()
        keys = sorted({row["order_id"] for row in incoming})
        keys_processed += len(keys)
        if keys:
            current_scan = silver.scan(row_filter=In("order_id", keys))
            planned_files, planned_bytes = _planned_scan_cost(current_scan)
            files_planned += planned_files
            bytes_planned += planned_bytes
            current = current_scan.to_arrow().to_pylist()
        else:
            current = []
        try:
            collapsed = collapse_delta(incoming)
            current_by_key = {row["order_id"]: row for row in current}
            lower_versions_ignored += sum(
                1
                for row in collapsed
                if row["order_id"] in current_by_key
                and int(row["business_version"])
                < int(current_by_key[row["order_id"]]["business_version"])
            )
            resolved = resolve_against_current(current, incoming)
        except ValueError as exc:
            if "FF-14" in str(exc):
                ff14_conflicts += 1
            metrics.record(
                source="medallion",
                status="failed",
                ff14_conflicts=ff14_conflicts,
                keys_processed=keys_processed,
                files_planned=files_planned,
                bytes_planned=bytes_planned,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise

        if SIMULATE_B2_CRASH_BEFORE_COMMIT:
            os._exit(21)

        snapshot_id: int | None = None
        if resolved:
            previous_snapshot = silver.current_snapshot()
            previous_snapshot_id = (
                previous_snapshot.snapshot_id if previous_snapshot else None
            )
            silver.overwrite(
                _rows_to_silver(resolved),
                overwrite_filter=In(
                    "order_id", sorted({row["order_id"] for row in resolved})
                ),
                snapshot_properties={
                    SILVER_WORK_ID_KEY: load_id,
                    "changed-keys": str(len(resolved)),
                },
            )
            snapshot = silver.current_snapshot()
            snapshot_id = snapshot.snapshot_id if snapshot else None
            if snapshot_id != previous_snapshot_id:
                snapshot_delta += 1
                (
                    removed_files,
                    added_files,
                    removed_bytes,
                    added_bytes,
                ) = _snapshot_write_cost(snapshot)
                files_removed += removed_files
                files_added += added_files
                bytes_removed += removed_bytes
                bytes_added += added_bytes

        if SIMULATE_B2_CRASH_AFTER_COMMIT:
            os._exit(22)

        _mark_b2_completed(
            fs,
            progress,
            record,
            snapshot_id,
            [row["order_id"] for row in resolved],
            source_epoch_id=_source_epoch_id(incoming),
            output_digest=_rows_output_digest(resolved),
        )
        processed += 1
        files_processed += len(record["bronze_data_files"])

    metrics.record(
        source="medallion",
        status="success",
        silver_rows=processed,
        files_processed=files_processed,
        keys_processed=keys_processed,
        lower_versions_ignored=lower_versions_ignored,
        ff14_conflicts=ff14_conflicts,
        work_available=sum(
            record["load_id"] not in progress["completed"] for record in records
        ),
        work_in_flight=len(progress["work"]),
        work_completed=len(progress["completed"]),
        silver_duration_ms=int((time.monotonic() - started) * 1000),
        files_planned=files_planned,
        bytes_planned=bytes_planned,
        files_removed=files_removed,
        files_added=files_added,
        bytes_removed=bytes_removed,
        bytes_added=bytes_added,
        snapshot_delta=snapshot_delta,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def ensure_table(
    catalog: RestCatalog,
    identifier: str,
    schema: Schema,
    partition_spec: PartitionSpec,
) -> None:
    namespace = identifier.split(".")[0]
    catalog.create_namespace_if_not_exists(namespace)
    try:
        table = catalog.load_table(identifier)
    except NoSuchTableError:
        catalog.create_table(
            identifier=identifier,
            schema=schema,
            partition_spec=partition_spec,
        )
        return

    # Keep the existing full-overwrite path readable while schemas migrate
    # additively. New fields are optional and receive nulls for old snapshots.
    schema_fn = getattr(table, "schema", None)
    update_schema_fn = getattr(table, "update_schema", None)
    if schema_fn is None or update_schema_fn is None:
        return
    existing_names = set(schema_fn().column_names)
    missing = [field for field in schema.columns if field.name not in existing_names]
    if not missing:
        return
    update = update_schema_fn()
    for field in missing:
        update.add_column(
            field.name,
            field.field_type,
            doc=field.doc,
            required=False,
        )
    update.commit()


_SILVER_TYPES: dict[str, pa.DataType] = {
    "order_id": pa.string(),
    "customer": pa.string(),
    "amount": pa.float64(),
    "country": pa.string(),
    "status": pa.string(),
    "event_time": pa.timestamp("us"),
    "kafka_timestamp": pa.timestamp("us"),
    "kafka_partition": pa.int32(),
    "kafka_offset": pa.int64(),
    "event_date": pa.date32(),
    "business_version": pa.int64(),
}


def _normalize_null_typed_columns(df: pa.Table) -> pa.Table:
    target_fields = [
        (
            pa.field(name, _SILVER_TYPES[name])
            if pa.types.is_null(df.schema.field(name).type) and name in _SILVER_TYPES
            else df.schema.field(name)
        )
        for name in df.column_names
    ]
    if all(t.type.equals(df.schema.field(t.name).type) for t in target_fields):
        return df
    return df.cast(pa.schema(target_fields))


def build_silver(df: pa.Table) -> pa.Table:
    if "business_version" not in df.column_names:
        df = df.append_column(
            "business_version",
            pa.array([None] * df.num_rows, type=pa.int64()),
        )
    df = _normalize_null_typed_columns(df)
    rows = df.to_pylist()
    if rows and any(row.get("business_version") is not None for row in rows):
        # The legacy rebuild remains a rollback path, but it must obey the
        # same domain contract as B2 whenever versioned observations exist.
        # In particular, equal-version payload conflicts cannot be resolved by
        # a transport offset tie-breaker.
        collapse_delta(rows)
    ordered = df.sort_by([("business_version", "descending")])
    aggs = [
        (name, "hash_first")
        for name in [
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "kafka_timestamp",
            "event_date",
            "kafka_partition",
            "kafka_offset",
            "business_version",
        ]
    ]
    deduped = ordered.group_by("order_id", use_threads=False).aggregate(aggs)
    deduped = deduped.rename_columns(
        [
            "order_id",
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "kafka_timestamp",
            "event_date",
            "kafka_partition",
            "kafka_offset",
            "business_version",
        ]
    )
    return deduped.select(
        [
            "order_id",
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "kafka_timestamp",
            "kafka_partition",
            "kafka_offset",
            "event_date",
            "business_version",
        ]
    )


def build_gold(df: pa.Table) -> pa.Table:
    grouped = df.group_by(["event_date", "country", "status"]).aggregate(
        [
            ("order_id", "count"),
            ("amount", "sum"),
            ("amount", "mean"),
            ("customer", "count_distinct"),
        ]
    )
    return grouped.rename_columns(
        [
            "event_date",
            "country",
            "status",
            "orders_count",
            "total_amount",
            "avg_amount",
            "distinct_customers",
        ]
    )


SHADOW_BUSINESS_COLUMNS = (
    "business_version",
    "customer",
    "amount",
    "country",
    "status",
    "event_time",
    "event_date",
)
SHADOW_EXCLUDED_COLUMNS = (
    "kafka_timestamp",
    "kafka_partition",
    "kafka_offset",
)


@dataclass(frozen=True)
class BronzeBoundary:
    """One materialized Bronze snapshot used by both shadow candidates."""

    rows: pa.Table
    snapshot_id: int | None


def _shadow_value(value):
    if value is None:
        return ("null",)
    if isinstance(value, float) and math.isnan(value):
        return ("nan",)
    if isinstance(value, (datetime, date)):
        return (type(value).__name__, value.isoformat())
    return (type(value).__name__, value)


def _shadow_rows_by_key(
    table: pa.Table | list[dict],
) -> tuple[dict[str, dict], list[dict]]:
    rows = table.to_pylist() if isinstance(table, pa.Table) else list(table)
    rows_by_key: dict[str, list[dict]] = {}
    for row in rows:
        rows_by_key.setdefault(row.get("order_id"), []).append(row)

    by_key: dict[str, dict] = {}
    duplicates: list[dict] = []
    for key in sorted(rows_by_key, key=str):
        ordered_rows = sorted(
            rows_by_key[key],
            key=lambda row: tuple(
                (column, repr(_shadow_value(row.get(column)))) for column in sorted(row)
            ),
        )
        by_key[key] = ordered_rows[0]
        duplicates.extend(
            {
                "order_id": key,
                "mismatch_type": "duplicate_business_key",
            }
            for _ in ordered_rows[1:]
        )
    return by_key, duplicates


def compare_business_state(
    legacy: pa.Table | list[dict],
    persisted_b2: pa.Table | list[dict],
) -> dict:
    """Compare logical current-state rows, excluding transport-only metadata."""

    legacy_by_key, legacy_duplicates = _shadow_rows_by_key(legacy)
    b2_by_key, b2_duplicates = _shadow_rows_by_key(persisted_b2)
    mismatches = [{**item, "side": "legacy"} for item in legacy_duplicates] + [
        {**item, "side": "persisted_b2"} for item in b2_duplicates
    ]

    for order_id in sorted(set(legacy_by_key) | set(b2_by_key), key=str):
        legacy_row = legacy_by_key.get(order_id)
        b2_row = b2_by_key.get(order_id)
        if legacy_row is None:
            mismatches.append(
                {"order_id": order_id, "mismatch_type": "missing_in_legacy"}
            )
            continue
        if b2_row is None:
            mismatches.append(
                {"order_id": order_id, "mismatch_type": "missing_in_persisted_b2"}
            )
            continue

        differing_columns = [
            column
            for column in SHADOW_BUSINESS_COLUMNS
            if _shadow_value(legacy_row.get(column))
            != _shadow_value(b2_row.get(column))
        ]
        if differing_columns:
            mismatch_type = (
                "business_version_mismatch"
                if differing_columns == ["business_version"]
                else "payload_mismatch"
            )
            mismatches.append(
                {
                    "order_id": order_id,
                    "mismatch_type": mismatch_type,
                    "legacy_business_version": legacy_row.get("business_version"),
                    "b2_business_version": b2_row.get("business_version"),
                    "differing_columns": differing_columns,
                }
            )

    mismatches.sort(
        key=lambda item: (
            str(item.get("order_id")),
            item.get("mismatch_type", ""),
            item.get("side", ""),
        )
    )
    return {
        "equal": not mismatches,
        "mismatches": mismatches,
        "compared_keys": len(set(legacy_by_key) | set(b2_by_key)),
        "excluded_columns": list(SHADOW_EXCLUDED_COLUMNS),
    }


def run_quality_checks(df: pa.Table) -> dict[str, int]:
    checks: dict[str, int] = {}

    def count(mask: pa.ChunkedArray) -> int:
        value = pc.sum(mask.cast(pa.int64()))
        return int(value.as_py()) if value is not None else 0

    if "order_id" in df.column_names:
        checks["order_id_null"] = count(pc.is_null(df["order_id"]))
    if "amount" in df.column_names:
        checks["amount_null_or_nonpositive"] = count(
            pc.or_kleene(pc.is_null(df["amount"]), pc.less_equal(df["amount"], 0))
        )
    if "country" in df.column_names:
        checks["country_null"] = count(pc.is_null(df["country"]))
    if "status" in df.column_names:
        valid = pc.is_in(df["status"], value_set=pa.array(VALID_STATUSES)).fill_null(
            False
        )
        checks["status_invalid"] = count(pc.invert(valid))
    if "event_time" in df.column_names:
        checks["event_time_null"] = count(pc.is_null(df["event_time"]))

    return {name: value for name, value in checks.items() if value}


def _snapshot_id(table) -> int | None:
    current_snapshot = getattr(table, "current_snapshot", None)
    if callable(current_snapshot):
        snapshot = current_snapshot()
        if snapshot is not None:
            return getattr(snapshot, "snapshot_id", None)
    metadata = getattr(table, "metadata", None)
    return getattr(metadata, "current_snapshot_id", None)


def _pin_bronze_boundary(catalog: RestCatalog) -> BronzeBoundary | None:
    bronze_id = f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}"
    try:
        bronze = catalog.load_table(bronze_id)
    except NoSuchTableError:
        return None
    return BronzeBoundary(
        rows=bronze.scan().to_arrow(),
        snapshot_id=_snapshot_id(bronze),
    )


def _load_bronze_df(catalog: RestCatalog) -> pa.Table | None:
    boundary = _pin_bronze_boundary(catalog)
    return boundary.rows if boundary is not None else None


def _legacy_silver_cycle(catalog: RestCatalog, metrics: Metrics) -> dict | None:
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    bronze_df = _load_bronze_df(catalog)
    if bronze_df is None:
        print("Bronze table not available yet; skipping cycle", flush=True)
        return None

    started = time.monotonic()
    violations_total = 0

    violations = run_quality_checks(bronze_df)
    if violations:
        details = ", ".join(f"{name}={value}" for name, value in violations.items())
        print(f"Quality violations on bronze batch: {details}", flush=True)
        violations_total = sum(violations.values())
        if FAIL_ON_VIOLATIONS:
            print(
                "QUALITY_FAIL_ON_VIOLATIONS is set -> aborting cycle",
                file=sys.stderr,
                flush=True,
            )
            metrics.record(
                source="medallion",
                status="failed",
                bronze_rows=bronze_df.num_rows,
                quality_violations=violations_total,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return

    silver_df = build_silver(bronze_df)
    ensure_table(catalog, silver_id, SILVER_SCHEMA, SILVER_PARTITION_SPEC)
    silver = catalog.load_table(silver_id)
    silver.overwrite(silver_df)
    duplicates_removed = bronze_df.num_rows - silver_df.num_rows
    print(
        f"Silver {silver_id}: overwritten with {silver_df.num_rows} "
        f"deduplicated orders ({duplicates_removed} duplicates removed)",
        flush=True,
    )
    return {
        "bronze_df": bronze_df,
        "silver_df": silver_df,
        "violations_total": violations_total,
        "started": started,
    }


def _write_gold(catalog: RestCatalog, gold_df: pa.Table) -> None:
    gold_id = f"{GOLD_NAMESPACE}.{GOLD_TABLE}"
    ensure_table(catalog, gold_id, GOLD_SCHEMA, PartitionSpec())
    gold = catalog.load_table(gold_id)
    gold.overwrite(gold_df)
    print(
        f"Gold {gold_id}: overwritten with {gold_df.num_rows} daily metrics",
        flush=True,
    )


def _read_persisted_silver(catalog: RestCatalog) -> pa.Table:
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    silver = catalog.load_table(silver_id)
    return silver.scan().to_arrow()


def _run_legacy(catalog: RestCatalog, metrics: Metrics) -> None:
    cycle = _legacy_silver_cycle(catalog, metrics)
    if cycle is None:
        return

    gold_started = time.monotonic()
    gold_df = build_gold(cycle["silver_df"])
    _write_gold(catalog, gold_df)
    gold_duration_ms = int((time.monotonic() - gold_started) * 1000)

    metrics.record(
        source="medallion",
        status="success",
        bronze_rows=cycle["bronze_df"].num_rows,
        silver_rows=cycle["silver_df"].num_rows,
        gold_rows=gold_df.num_rows,
        duplicates_removed=(cycle["bronze_df"].num_rows - cycle["silver_df"].num_rows),
        quality_violations=cycle["violations_total"],
        duration_ms=int((time.monotonic() - cycle["started"]) * 1000),
        silver_duration_ms=int((gold_started - cycle["started"]) * 1000),
        gold_duration_ms=gold_duration_ms,
    )


def _run_m4(catalog: RestCatalog, metrics: Metrics, selected_mode: str) -> None:
    if GOLD_SOURCE not in {"legacy", "persisted_silver"}:
        raise ValueError(f"Unsupported GOLD_SOURCE: {GOLD_SOURCE}")

    started = time.monotonic()
    legacy_silver_df: pa.Table | None = None
    bronze_df: pa.Table | None = None
    violations_total = 0

    if selected_mode == "b2":
        # Pin Bronze before B2 runs.  Both the legacy candidate and the B2
        # result must describe this same logical source boundary; a later live
        # Bronze scan would make shadow evidence race with ingestion.
        bronze_boundary = None
        if GOLD_SOURCE == "legacy" or SHADOW_COMPARE_ENABLED:
            bronze_boundary = _pin_bronze_boundary(catalog)
            bronze_df = bronze_boundary.rows if bronze_boundary is not None else None
        run_b2(catalog, metrics)
        if bronze_boundary is not None:
            legacy_silver_df = build_silver(bronze_boundary.rows)
    else:
        cycle = _legacy_silver_cycle(catalog, metrics)
        if cycle is None:
            return
        bronze_df = cycle["bronze_df"]
        legacy_silver_df = cycle["silver_df"]
        violations_total = cycle["violations_total"]

    persisted_silver_df = _read_persisted_silver(catalog)
    if SHADOW_COMPARE_ENABLED:
        if legacy_silver_df is None:
            raise RuntimeError(
                "Shadow comparison requires a legacy business projection"
            )
        comparison = compare_business_state(legacy_silver_df, persisted_silver_df)
        if not comparison["equal"]:
            diagnostic = json.dumps(
                comparison["mismatches"], sort_keys=True, default=str
            )
            print(
                f"Shadow comparison mismatch: {diagnostic}", file=sys.stderr, flush=True
            )
            metrics.record(
                source="medallion",
                status="shadow_failed",
                shadow_comparisons=1,
                shadow_mismatches=len(comparison["mismatches"]),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise ValueError(f"Shadow comparison failed: {diagnostic}")

    gold_started = time.monotonic()
    if GOLD_SOURCE == "legacy":
        if legacy_silver_df is None:
            raise RuntimeError("GOLD_SOURCE=legacy requires a legacy Silver projection")
        gold_input = legacy_silver_df
    else:
        gold_input = persisted_silver_df

    gold_df = build_gold(gold_input)
    _write_gold(catalog, gold_df)
    gold_duration_ms = int((time.monotonic() - gold_started) * 1000)
    metrics.record(
        source="medallion",
        status="success",
        bronze_rows=bronze_df.num_rows if bronze_df is not None else None,
        silver_rows=gold_input.num_rows,
        gold_rows=gold_df.num_rows,
        duplicates_removed=(
            bronze_df.num_rows - legacy_silver_df.num_rows
            if bronze_df is not None and legacy_silver_df is not None
            else None
        ),
        quality_violations=violations_total,
        duration_ms=int((time.monotonic() - started) * 1000),
        shadow_comparisons=int(SHADOW_COMPARE_ENABLED),
        shadow_mismatches=0,
        silver_duration_ms=int((gold_started - started) * 1000),
        gold_duration_ms=gold_duration_ms,
    )


def run(
    catalog: RestCatalog,
    metrics: Metrics,
    mode: str | None = None,
) -> None:
    selected_mode = (mode or SILVER_MODE).lower()
    if selected_mode == "b2":
        _run_m4(catalog, metrics, selected_mode)
        return
    if selected_mode != "legacy":
        raise ValueError(f"Unsupported SILVER_MODE: {selected_mode}")
    if GOLD_SOURCE == "legacy" and not SHADOW_COMPARE_ENABLED:
        _run_legacy(catalog, metrics)
    else:
        _run_m4(catalog, metrics, selected_mode)


def main() -> None:
    validate_runtime_config(RUNTIME_CONFIG)
    print(f"Iceberg medallion service started (silver mode: {SILVER_MODE})", flush=True)
    catalog = get_catalog()
    metrics = Metrics()
    while True:
        try:
            run(catalog, metrics)
        except Exception as exc:
            print(f"Medallion error: {exc}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()  # pragma: no cover
