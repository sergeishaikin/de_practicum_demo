from __future__ import annotations

import os
import sys
import time
import uuid
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
MEDALLION_SHADOW_RECEIPT_PATH = os.getenv(
    "MEDALLION_SHADOW_RECEIPT_PATH",
    "streaming/medallion/shadow-certification.json",
)
MAX_COMPLETED_PROGRESS = int(os.getenv("MAX_COMPLETED_PROGRESS", "100"))
SIMULATE_B2_CRASH_BEFORE_COMMIT = (
    os.getenv("SIMULATE_B2_CRASH_BEFORE_COMMIT", "0") == "1"
)
SIMULATE_B2_CRASH_AFTER_COMMIT = os.getenv("SIMULATE_B2_CRASH_AFTER_COMMIT", "0") == "1"

SILVER_WORK_ID_KEY = "silver-work-id"
# Stamped on every Gold commit that was built from persisted Silver: the
# identity of the Silver snapshot that produced the Gold state.  Same idiom as
# `SILVER_WORK_ID_KEY` and the writer's `load-id` -- the catalog carries the
# provenance, so no sidecar file can disagree with the table.
GOLD_SOURCE_SILVER_SNAPSHOT_KEY = "source-silver-snapshot-id"
PROGRESS_VERSION = 1
# Bumped whenever the stored receipt's shape changes.  A receipt written by any
# other version reads as absent, which means "run the comparison".
SHADOW_RECEIPT_VERSION = 1

# The first token of the one stdout line a completed cycle prints.  It is the
# integration harness's liveness signal, so the line's shape is a contract, not
# a log message: see `CycleOutcome` for the vocabulary and
# `tests/support/medallion_harness.py:parse_cycle_marker` for the reader.
CYCLE_COMPLETE_MARKER = "cycle-complete"

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
    """Read a small JSON object sequentially, never by its advertised size.

    `open_input_file` is random access: it takes the object's length from a HEAD
    at open and applies that length to the body it later fetches. These objects
    are overwritten in place and they shrink - completing a work item replaces a
    `work` entry holding full object paths with a compact `completed` one - so a
    read issued across that overwrite is sized from the larger predecessor and
    served the smaller successor. PyArrow returns the whole over-sized buffer,
    and the tail is process memory that was never written.

    Observed in CI on 2026-08-19: a 236-byte document returned as 521 bytes whose
    last 285 were heap pointers and stray literals, while a second read and a
    sequential read of the same object both returned the intact 236 bytes with an
    identical digest. Evidence in the archived change
    `diagnose-medallion-progress-read-corruption`.

    `open_input_stream` reads the body to EOF, so it cannot be sized by a stale
    HEAD. Same bytes, same parse, same failure on a genuinely bad object.
    """

    with fs.open_input_stream(path) as source:
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


def _shadow_receipt_path() -> str:
    return _storage_path(MEDALLION_SHADOW_RECEIPT_PATH)


def load_shadow_receipt(fs: S3FileSystem) -> dict | None:
    """Read the shadow certification receipt, or ``None`` if it cannot be trusted.

    Deliberately asymmetric with the neighbouring ``load_completion_ledger``,
    which *raises* on an unusable receipt.  That asymmetry is a decision, not an
    inconsistency: an ambiguous completion receipt is two contradictory claims
    about one load id -- a correctness fork worth stopping the service for --
    whereas an unusable shadow certificate only means "not certified".  So every
    failure here degrades to ``None``, which the caller reads as "run the
    comparison".  Failing toward doing the work is the only safe direction, since
    the thing being skipped is a correctness gate.

    Absent, unreadable, malformed and wrong-version receipts are all the same
    answer.  Nothing is trusted partially: a receipt is either a well-formed
    object of the expected version or it is not a receipt.
    """

    path = _shadow_receipt_path()
    try:
        receipt = _read_json(fs, path)
    except FileNotFoundError:
        return None
    except Exception as exc:
        # Identifiers and the failure only: a receipt read must never be able to
        # widen what a diagnostic discloses.
        print(
            f"Shadow certification receipt unreadable ({path}): "
            f"{type(exc).__name__}",
            file=sys.stderr,
            flush=True,
        )
        return None
    if not isinstance(receipt, dict):
        return None
    if receipt.get("version") != SHADOW_RECEIPT_VERSION:
        return None
    return receipt


def save_shadow_receipt(fs: S3FileSystem, receipt: dict) -> None:
    """Certify a passing comparison durably, best-effort.

    Swallow-and-continue in the style of ``Metrics.record``, and **only** on the
    write side: a receipt that never lands costs exactly one redundant
    comparison next cycle, whereas a read failure treated as success would skip
    a correctness gate.  Those two contracts are opposite, which is why they are
    two functions.
    """

    try:
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with fs.open_output_stream(_shadow_receipt_path()) as output:
            output.write(raw)
    except Exception as exc:
        print(
            f"Shadow certification receipt not persisted for cycle "
            f"{receipt.get('cycle_id')}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )


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
    catalog: RestCatalog,
    metrics: Metrics,
    fs: S3FileSystem | None = None,
    *,
    cycle_id: str | None = None,
) -> B2Outcome | None:
    """Process committed Bronze outbox work with the B2 Silver projection."""

    fs = fs or get_fs()
    # Generated here when called directly, so the existing direct-call unit tests
    # keep working unchanged; _run_m4 always supplies the enclosing cycle's id.
    cycle_id = cycle_id or uuid.uuid4().hex
    bronze_id = f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}"
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    try:
        bronze = catalog.load_table(bronze_id)
    except NoSuchTableError:
        print("Bronze table not available yet; skipping B2 cycle", flush=True)
        return None

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

    duration_ms = int((time.monotonic() - started) * 1000)
    work_available = sum(
        record["load_id"] not in progress["completed"] for record in records
    )
    outcome = B2Outcome(
        duration_ms=duration_ms,
        silver_rows=processed,
        files_processed=files_processed,
        keys_processed=keys_processed,
        lower_versions_ignored=lower_versions_ignored,
        ff14_conflicts=ff14_conflicts,
        work_available=work_available,
        work_in_flight=len(progress["work"]),
        work_completed=len(progress["completed"]),
        files_planned=files_planned,
        bytes_planned=bytes_planned,
        files_removed=files_removed,
        files_added=files_added,
        bytes_removed=bytes_removed,
        bytes_added=bytes_added,
        snapshot_delta=snapshot_delta,
        silver_snapshot_id=_snapshot_id(silver),
    )
    # `silver_duration_ms` is deliberately absent: it keeps its inclusive
    # whole-cycle meaning and is populated only on the `cycle` record, so
    # historical rows stay byte-for-byte interpretable.
    metrics.record(
        source="medallion",
        status="success",
        phase="b2",
        cycle_id=cycle_id,
        silver_rows=outcome.silver_rows,
        files_processed=outcome.files_processed,
        keys_processed=outcome.keys_processed,
        lower_versions_ignored=outcome.lower_versions_ignored,
        ff14_conflicts=outcome.ff14_conflicts,
        work_available=outcome.work_available,
        work_in_flight=outcome.work_in_flight,
        work_completed=outcome.work_completed,
        files_planned=outcome.files_planned,
        bytes_planned=outcome.bytes_planned,
        files_removed=outcome.files_removed,
        files_added=outcome.files_added,
        bytes_removed=outcome.bytes_removed,
        bytes_added=outcome.bytes_added,
        snapshot_delta=outcome.snapshot_delta,
        silver_snapshot_id=outcome.silver_snapshot_id,
        duration_ms=outcome.duration_ms,
    )
    return outcome


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

# Hand-bumped whenever `compare_business_state` changes what it *means* by
# equality -- a different duplicate-resolution rule, a new mismatch class, a
# changed null/NaN convention.  It is half of the projection identity because a
# hand-maintained constant on its own is a silent-staleness hazard: a contract
# change nobody remembered to bump would keep certifying comparisons made under
# the old contract.  The digest below is the other half, and it moves on its own.
SHADOW_CONTRACT_VERSION = 1


def _shadow_projection_identity() -> str:
    """Identity of *what* a shadow comparison checks.

    Two halves, because neither is sufficient alone.  The `sha256` digest covers
    the column classification -- the most likely real change -- and invalidates
    every outstanding certificate automatically the moment a column is added,
    removed or reclassified.  `SHADOW_CONTRACT_VERSION` covers the semantic
    changes the column tuples cannot see.  The two tuples are rendered with a
    separator between them so that moving a column from one to the other is a
    different string, not the same multiset.
    """

    canonical = "|".join(
        ("business",)
        + SHADOW_BUSINESS_COLUMNS
        + ("excluded",)
        + SHADOW_EXCLUDED_COLUMNS
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"contract={SHADOW_CONTRACT_VERSION};columns={digest}"


def _runtime_identity(selected_mode: str) -> str:
    """Identity of the runtime a certificate was produced under.

    The *effective* mode rather than `SILVER_MODE`, because `run()` accepts an
    explicit mode; plus the two rollout switches that decide which projections
    exist at all and whether they are compared.  A certificate produced in the
    `shadow` stage therefore cannot authorise a skip in `cutover`, where the
    comparison's conclusion is what puts the incremental state in front of
    consumers.
    """

    return (
        f"mode={selected_mode};gold_source={GOLD_SOURCE};"
        f"shadow_compare={'1' if SHADOW_COMPARE_ENABLED else '0'}"
    )


def shadow_receipt_is_valid(
    receipt: dict | None,
    *,
    bronze_snapshot_id: int | None,
    silver_snapshot_id: int | None,
    runtime_identity: str,
    projection_identity: str,
) -> bool:
    """True only when this receipt certifies exactly the state about to be skipped.

    Pure, so the fast-path decision can be specified without a filesystem.  A
    skipped comparison is a skipped correctness gate, so this answers `True` only
    when the previous comparison passed *and* all four identities match; every
    other input -- including no receipt at all -- answers `False` and the caller
    does the work.

    A `None` current snapshot id never matches, not even a stored `null`.
    `_snapshot_id` legitimately returns `None` for a table with no snapshots, and
    `None == None` must never certify an empty or unknown lake.
    """

    if not isinstance(receipt, dict):
        return False
    if bronze_snapshot_id is None or silver_snapshot_id is None:
        return False
    if receipt.get("result") != "equal":
        return False
    return (
        receipt.get("bronze_snapshot_id") == bronze_snapshot_id
        and receipt.get("silver_snapshot_id") == silver_snapshot_id
        and receipt.get("runtime_identity") == runtime_identity
        and receipt.get("projection_identity") == projection_identity
    )


@dataclass(frozen=True)
class B2Outcome:
    """The physical cost one ``run_b2`` pass measured, rolled up for the caller.

    ``_run_m4`` copies these onto the ``cycle`` record so the Prometheus gauges
    carry the incremental writer's real numbers.  Before 04-02 the outer record
    published them as zeros, resetting the nested record's gauges seconds after
    they were measured.
    """

    duration_ms: int
    silver_rows: int
    files_processed: int
    keys_processed: int
    lower_versions_ignored: int
    ff14_conflicts: int
    work_available: int
    work_in_flight: int
    work_completed: int
    files_planned: int
    bytes_planned: int
    files_removed: int
    files_added: int
    bytes_removed: int
    bytes_added: int
    snapshot_delta: int
    silver_snapshot_id: int | None


@dataclass(frozen=True)
class BronzeBoundary:
    """One materialized Bronze snapshot used by both shadow candidates."""

    rows: pa.Table
    snapshot_id: int | None


@dataclass(frozen=True)
class CycleOutcome:
    """What one *completed* cycle decided, rendered as the stdout marker.

    Only a cycle that ran to the end produces one.  A cycle that returned early
    (no Bronze table) or aborted (a shadow mismatch, a fatal quality violation)
    returns ``None`` and stays silent, because "no marker" is precisely how the
    integration harness learns that a deployment did not complete.

    The vocabulary is fixed here for the rest of the phase, since
    ``tests/support/medallion_harness.py`` parses the rendered line:

    * ``gold`` — ``"rebuilt"`` when Gold was overwritten, ``"skipped"`` when the
      cycle decided Gold was already current.  Both are reachable since GLD-01:
      ``"skipped"`` means the current Gold snapshot already records the persisted
      Silver snapshot this cycle would have rebuilt Gold from.
    * ``shadow`` — ``"compared"`` when the two Silver projections were checked,
      ``"skipped"`` when the comparison was deliberately not run for this cycle,
      ``"disabled"`` when ``SHADOW_COMPARE`` is off.  Both are reachable since
      SHD-01: ``"skipped"`` means a durable certificate still names this cycle's
      Bronze snapshot, Silver snapshot, runtime and projection contract, so the
      comparison's conclusion is already known.

    ``duration_ms`` is the same number the ``cycle`` metrics record carries, so
    a log line and a metrics row about the same cycle never disagree.
    """

    cycle_id: str
    gold: str
    shadow: str
    duration_ms: int


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


def _bronze_snapshot_id(catalog: RestCatalog) -> int | None:
    """The current Bronze snapshot id, read from table metadata -- never a scan.

    This is what makes the fast path cheap: the decision to skip a full Bronze
    scan must not itself cost a full Bronze scan.  ``None`` for a table that does
    not exist yet or has never been committed to, and ``None`` certifies nothing,
    so an unknown Bronze always means do the work.
    """

    try:
        return _snapshot_id(catalog.load_table(f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}"))
    except NoSuchTableError:
        return None


def _silver_snapshot_id(catalog: RestCatalog) -> int | None:
    """The current persisted-Silver snapshot id, metadata only -- never a scan.

    Read *before* the incremental writer runs, because the certificate gates the
    Bronze pin and the pin has to happen before the writer.  It is deliberately
    not the id returned by ``_read_persisted_silver``: that one is read after the
    writer, is what Gold is built from and what the receipt certifies, and using
    it here would either move the pin after the writer -- making shadow evidence
    race with ingestion -- or move the persisted-Silver read before it, leaving
    Gold a cycle stale.  Both are contracts this phase already fixed.

    Reading it early is safe in the direction that matters: a writer pass can
    only move Silver when it finds committed outbox work, and committed outbox
    work implies a Bronze append, which moves the Bronze snapshot id and
    invalidates the certificate on its own.
    """

    try:
        return _snapshot_id(catalog.load_table(f"{SILVER_NAMESPACE}.{SILVER_TABLE}"))
    except NoSuchTableError:
        return None


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


def _legacy_silver_cycle(
    catalog: RestCatalog, metrics: Metrics, *, cycle_id: str | None = None
) -> dict | None:
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
                phase="cycle",
                cycle_id=cycle_id,
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


def _gold_provenance(gold) -> int | None:
    """Return the persisted Silver snapshot id the **current** Gold state records.

    Read from ``gold.current_snapshot()`` and from nothing else.  Walking the
    table's whole snapshot history for the most recent property-bearing snapshot
    would be fail-open: an expired or superseded snapshot could vouch for a Gold state that
    something else has since replaced.  Trino maintenance is exactly that case --
    ``dags/lakehouse_maintenance.py`` lists ``("gold", "orders_daily_metrics")`` in
    ``MAINTENANCE_TABLES``, and ``optimize`` / ``expire_snapshots`` rewrite Gold's
    files while knowing nothing about this property.  Reading only the current
    snapshot makes such a rewrite invalidate provenance automatically: it reads as
    absent and the medallion rebuilds Gold once.  That is the security-relevant
    property of this change.

    ``None`` means "cannot certify", and is returned for a table with no current
    snapshot, a snapshot without the property, and a property whose value does not
    parse as an integer.  Snapshot-property values are strings written by whoever
    last committed, so they are parsed defensively rather than trusted.
    """

    current_snapshot = getattr(gold, "current_snapshot", None)
    if not callable(current_snapshot):
        return None
    snapshot = current_snapshot()
    if snapshot is None:
        return None
    summary = getattr(snapshot, "summary", None)
    properties = getattr(summary, "additional_properties", None) or {}
    raw = properties.get(GOLD_SOURCE_SILVER_SNAPSHOT_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _write_gold(
    catalog: RestCatalog,
    gold_df: pa.Table,
    *,
    source_silver_snapshot_id: int | None,
) -> tuple[bool, int | None]:
    """Rebuild Gold unless the current Gold state was already built from this Silver.

    Returns ``(written, gold_snapshot_id)``.  This is memoization, not
    incrementalisation: when the write happens it is the same full, exactly
    verifiable rebuild D-4 requires.  What is elided is a rebuild whose result is
    provably identical to the Gold state already in the catalog.

    ``source_silver_snapshot_id`` is the whole mode switch, which is why nothing in
    here branches on ``GOLD_SOURCE``.  A caller with no persisted-Silver basis --
    the legacy Gold source, whose input is an in-memory rebuild derived from Bronze
    -- passes ``None``, and therefore always writes and never stamps.  ``None``
    also never matches ``_gold_provenance``: ``None == None`` must not certify Gold
    against an empty lake.
    """

    gold_id = f"{GOLD_NAMESPACE}.{GOLD_TABLE}"
    ensure_table(catalog, gold_id, GOLD_SCHEMA, PartitionSpec())
    gold = catalog.load_table(gold_id)

    if (
        source_silver_snapshot_id is not None
        and source_silver_snapshot_id == _gold_provenance(gold)
    ):
        # Deliberately no "stamp-only" empty overwrite to refresh provenance: a
        # full overwrite's APPEND half is not elided for an empty frame, so it
        # would write a snapshot anyway -- defeating the skip and growing the
        # history the maintenance DAG then has to compact.
        print(
            f"Gold {gold_id}: already built from persisted Silver snapshot "
            f"{source_silver_snapshot_id}; rebuild skipped",
            flush=True,
        )
        return False, _snapshot_id(gold)

    if source_silver_snapshot_id is None:
        gold.overwrite(gold_df)
    else:
        gold.overwrite(
            gold_df,
            snapshot_properties={
                GOLD_SOURCE_SILVER_SNAPSHOT_KEY: str(source_silver_snapshot_id)
            },
        )
    print(
        f"Gold {gold_id}: overwritten with {gold_df.num_rows} daily metrics",
        flush=True,
    )
    return True, _snapshot_id(gold)


def _read_persisted_silver(catalog: RestCatalog) -> tuple[pa.Table, int | None]:
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    silver = catalog.load_table(silver_id)
    return silver.scan().to_arrow(), _snapshot_id(silver)


def _run_legacy(
    catalog: RestCatalog, metrics: Metrics, *, cycle_id: str | None = None
) -> CycleOutcome | None:
    cycle_id = cycle_id or uuid.uuid4().hex
    cycle = _legacy_silver_cycle(catalog, metrics, cycle_id=cycle_id)
    if cycle is None:
        # No Bronze, or a fatal quality violation: no cycle completed, so the
        # caller must not announce one.
        return None

    gold_started = time.monotonic()
    gold_df = build_gold(cycle["silver_df"])
    # The legacy Gold input is the in-memory rebuild derived from Bronze, not
    # persisted Silver, so a persisted-Silver provenance stamp would not describe
    # it: this path passes no basis, always writes and never stamps.
    gold_written, gold_snapshot_id = _write_gold(
        catalog, gold_df, source_silver_snapshot_id=None
    )
    ended = time.monotonic()
    duration_ms = int((ended - cycle["started"]) * 1000)

    # The legacy path is one undivided phase: it emits exactly one record, and
    # `silver_duration_ms` / `gold_duration_ms` keep today's inclusive meaning.
    metrics.record(
        source="medallion",
        status="success",
        phase="cycle",
        cycle_id=cycle_id,
        bronze_rows=cycle["bronze_df"].num_rows,
        silver_rows=cycle["silver_df"].num_rows,
        gold_rows=gold_df.num_rows,
        duplicates_removed=(cycle["bronze_df"].num_rows - cycle["silver_df"].num_rows),
        quality_violations=cycle["violations_total"],
        duration_ms=duration_ms,
        silver_duration_ms=int((gold_started - cycle["started"]) * 1000),
        gold_duration_ms=int((ended - gold_started) * 1000),
        gold_snapshot_id=gold_snapshot_id,
        gold_skipped=not gold_written,
    )
    # The legacy rollout state is (legacy, legacy, SHADOW_COMPARE=0), so this
    # path never compares projections and always overwrites Gold.  What
    # `_write_gold` did is reported rather than asserted, so the marker can never
    # claim a rebuild the write path did not perform.
    return CycleOutcome(
        cycle_id=cycle_id,
        gold="rebuilt" if gold_written else "skipped",
        shadow="disabled",
        duration_ms=duration_ms,
    )


def _run_m4(
    catalog: RestCatalog,
    metrics: Metrics,
    selected_mode: str,
    *,
    cycle_id: str | None = None,
    fs: S3FileSystem | None = None,
) -> CycleOutcome | None:
    if GOLD_SOURCE not in {"legacy", "persisted_silver"}:
        raise ValueError(f"Unsupported GOLD_SOURCE: {GOLD_SOURCE}")

    cycle_id = cycle_id or uuid.uuid4().hex
    started = time.monotonic()
    legacy_silver_df: pa.Table | None = None
    bronze_df: pa.Table | None = None
    violations_total = 0
    outcome: B2Outcome | None = None
    b2_window = 0.0

    # Under GOLD_SOURCE=legacy the legacy projection is Gold's *input*, so the
    # Bronze pin and the rebuild are required work rather than validation work
    # and no certificate can authorise skipping them.  Skipping them there would
    # break the cycle, not optimise it.
    needs_legacy_projection = GOLD_SOURCE == "legacy"

    # Both reads are table metadata only, so the decision to skip a full Bronze
    # scan costs no scan of its own.
    bronze_snapshot_id = _bronze_snapshot_id(catalog)
    runtime_identity = _runtime_identity(selected_mode)
    projection_identity = _shadow_projection_identity()
    # The pair the certificate is judged against.  `bronze_snapshot_id` is
    # reassigned below when a boundary is pinned, so the certified pair is kept
    # separately: it is what the post-writer revalidation compares to.
    certified_bronze_snapshot_id = bronze_snapshot_id
    certified_silver_snapshot_id: int | None = None
    shadow_certified = False
    if SHADOW_COMPARE_ENABLED:
        certified_silver_snapshot_id = _silver_snapshot_id(catalog)
        # The filesystem is touched only once both ids are known.  That is the
        # same fail-safe rule as everywhere else in this phase, and it is also
        # what keeps every in-memory double network-free: a double with no
        # snapshots has no ids, so no S3FileSystem is ever constructed for it.
        if bronze_snapshot_id is not None and certified_silver_snapshot_id is not None:
            shadow_certified = shadow_receipt_is_valid(
                load_shadow_receipt(fs if fs is not None else get_fs()),
                bronze_snapshot_id=bronze_snapshot_id,
                silver_snapshot_id=certified_silver_snapshot_id,
                runtime_identity=runtime_identity,
                projection_identity=projection_identity,
            )

    if selected_mode == "b2":
        # Pin Bronze before B2 runs.  Both the legacy candidate and the B2
        # result must describe this same logical source boundary; a later live
        # Bronze scan would make shadow evidence race with ingestion.
        pin_bronze = GOLD_SOURCE == "legacy" or SHADOW_COMPARE_ENABLED
        if shadow_certified and not needs_legacy_projection:
            pin_bronze = False
        bronze_boundary = _pin_bronze_boundary(catalog) if pin_bronze else None
        if bronze_boundary is not None:
            bronze_df = bronze_boundary.rows
            bronze_snapshot_id = bronze_boundary.snapshot_id
        b2_start = time.monotonic()
        outcome = run_b2(catalog, metrics, fs, cycle_id=cycle_id)
        b2_window = time.monotonic() - b2_start
        if bronze_boundary is not None:
            legacy_silver_df = build_silver(bronze_boundary.rows)
    else:
        cycle = _legacy_silver_cycle(catalog, metrics, cycle_id=cycle_id)
        if cycle is None:
            # No cycle completed, so no marker: see `CycleOutcome`.
            return None
        bronze_df = cycle["bronze_df"]
        legacy_silver_df = cycle["silver_df"]
        violations_total = cycle["violations_total"]

    # Unconditional, and deliberately so -- a recorded decision against research
    # Open Question 4, which asked whether the fast path should elide this read
    # too.  It feeds Gold at cutover, so coupling it to the Gold skip would
    # entangle SHD-01 and GLD-01 into one conditional and make each harder to
    # test alone; and the `shadow` phase duration now measures it directly, so a
    # later decision to elide it can be made on evidence instead of guesswork.
    persisted_silver_df, silver_snapshot_id = _read_persisted_silver(catalog)

    if shadow_certified:
        # The certificate was judged against metadata read *before* the
        # incremental writer ran, because the decision gates the Bronze pin and
        # the pin has to precede the writer.  That leaves a window: Bronze is
        # appended by a separate live process, and B2 itself can move Silver, so
        # the certified pair can stop describing the state Gold is about to be
        # published from.  Re-read both ids now -- table metadata only, never a
        # scan, and deliberately not a second Bronze boundary, which would be a
        # post-writer pin masquerading as a pre-writer one.
        current_bronze_snapshot_id = _bronze_snapshot_id(catalog)
        if (
            current_bronze_snapshot_id != certified_bronze_snapshot_id
            or silver_snapshot_id != certified_silver_snapshot_id
        ):
            shadow_certified = False
            if legacy_silver_df is None:
                # Nothing to compare against: the fast path skipped the pin, so
                # the only safe outcome is to publish nothing.  Like a mismatch,
                # this raise leaves `run()` without a `CycleOutcome`, so no
                # cycle-complete marker is printed.  The next cycle pins Bronze
                # and revalidates from scratch, because a stale certificate can
                # never certify the state that replaced it.
                raise ValueError(
                    "Shadow certificate went stale during the cycle: bronze "
                    f"{certified_bronze_snapshot_id} -> {current_bronze_snapshot_id}, "
                    f"silver {certified_silver_snapshot_id} -> {silver_snapshot_id}; "
                    "no legacy projection was built, so Gold is not published"
                )

    shadow_compared = False
    if SHADOW_COMPARE_ENABLED and not shadow_certified:
        if legacy_silver_df is None:
            raise RuntimeError(
                "Shadow comparison requires a legacy business projection"
            )
        comparison = compare_business_state(legacy_silver_df, persisted_silver_df)
        shadow_compared = True
        if not comparison["equal"]:
            diagnostic = json.dumps(
                comparison["mismatches"], sort_keys=True, default=str
            )
            print(
                f"Shadow comparison mismatch: {diagnostic}", file=sys.stderr, flush=True
            )
            # phase="cycle": this is an outer cycle that aborted before Gold,
            # not a nested phase that happened to fail.
            metrics.record(
                source="medallion",
                status="shadow_failed",
                phase="cycle",
                cycle_id=cycle_id,
                shadow_comparisons=1,
                shadow_mismatches=len(comparison["mismatches"]),
                bronze_snapshot_id=bronze_snapshot_id,
                silver_snapshot_id=silver_snapshot_id,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            # This raise leaves `run()` without a `CycleOutcome`, so no
            # cycle-complete marker is printed.  That is the contract, not an
            # oversight: the integration harness reads the absence of a marker
            # as "this deployment did not complete a cycle".
            raise ValueError(f"Shadow comparison failed: {diagnostic}")

        if bronze_snapshot_id is not None and silver_snapshot_id is not None:
            # Best-effort: a certificate that never lands costs exactly one
            # redundant comparison.  The ids written are the ones this
            # comparison actually validated -- the pinned Bronze boundary and
            # the persisted Silver that was compared against it.
            save_shadow_receipt(
                fs if fs is not None else get_fs(),
                {
                    "version": SHADOW_RECEIPT_VERSION,
                    "bronze_snapshot_id": bronze_snapshot_id,
                    "silver_snapshot_id": silver_snapshot_id,
                    "runtime_identity": runtime_identity,
                    "projection_identity": projection_identity,
                    "result": "equal",
                    "compared_keys": comparison["compared_keys"],
                    "certified_at": datetime.now(timezone.utc).isoformat(),
                    "cycle_id": cycle_id,
                },
            )

    # Enabled but not run means the certificate authorised the skip; disabled
    # means there was never a comparison to skip.
    shadow_skipped = SHADOW_COMPARE_ENABLED and not shadow_compared

    gold_started = time.monotonic()

    # The shadow segment is everything before Gold that was not the incremental
    # writer own window: the pinned Bronze scan, the legacy rebuild, the
    # persisted-Silver read and the comparison.  Because run_b2 starts its
    # internal timer only after it loads progress, the outbox listing and the
    # completion ledger, b2 + shadow + gold is *less than or equal to* the
    # cycle; the residual is the writer state-load preamble and is deliberately
    # attributed to no phase.  Under selected_mode == "legacy" there is no b2
    # record and the legacy Silver build falls inside this segment - that branch
    # is unreachable under any accepted rollout state, since
    # RUNTIME_ROLLOUT_MATRIX admits SILVER_MODE=legacy only as
    # ("legacy", "legacy", "0"), which run() routes to _run_legacy.  It is a
    # test-only artefact, not an operational claim.
    metrics.record(
        source="medallion",
        status="success",
        phase="shadow",
        cycle_id=cycle_id,
        shadow_comparisons=int(shadow_compared),
        shadow_skipped=shadow_skipped,
        shadow_mismatches=0,
        bronze_snapshot_id=bronze_snapshot_id,
        silver_snapshot_id=silver_snapshot_id,
        duration_ms=int(((gold_started - started) - b2_window) * 1000),
    )

    if GOLD_SOURCE == "legacy":
        if legacy_silver_df is None:
            raise RuntimeError("GOLD_SOURCE=legacy requires a legacy Silver projection")
        gold_input = legacy_silver_df
    else:
        gold_input = persisted_silver_df

    gold_df = build_gold(gold_input)
    # Only the persisted-Silver Gold source has a persisted-Silver basis to
    # certify against.  Under GOLD_SOURCE=legacy the Gold input is the in-memory
    # legacy rebuild, so no basis is passed and Gold is written every cycle
    # exactly as before.
    gold_written, gold_snapshot_id = _write_gold(
        catalog,
        gold_df,
        source_silver_snapshot_id=(
            silver_snapshot_id if GOLD_SOURCE == "persisted_silver" else None
        ),
    )
    ended = time.monotonic()
    gold_duration_ms = int((ended - gold_started) * 1000)
    cycle_duration_ms = int((ended - started) * 1000)

    metrics.record(
        source="medallion",
        status="success",
        phase="gold",
        cycle_id=cycle_id,
        gold_rows=gold_df.num_rows,
        silver_snapshot_id=silver_snapshot_id,
        gold_snapshot_id=gold_snapshot_id,
        gold_skipped=not gold_written,
        duration_ms=gold_duration_ms,
    )

    # A None outcome means "no physical cost measured", never a crashed cycle:
    # run_b2 returns None when Bronze is absent, and several suites stub it.
    metrics.record(
        source="medallion",
        status="success",
        phase="cycle",
        cycle_id=cycle_id,
        bronze_rows=bronze_df.num_rows if bronze_df is not None else None,
        silver_rows=gold_input.num_rows,
        gold_rows=gold_df.num_rows,
        duplicates_removed=(
            bronze_df.num_rows - legacy_silver_df.num_rows
            if bronze_df is not None and legacy_silver_df is not None
            else None
        ),
        quality_violations=violations_total,
        duration_ms=cycle_duration_ms,
        shadow_comparisons=int(shadow_compared),
        shadow_skipped=shadow_skipped,
        shadow_mismatches=0,
        silver_duration_ms=int((gold_started - started) * 1000),
        gold_duration_ms=gold_duration_ms,
        bronze_snapshot_id=bronze_snapshot_id,
        silver_snapshot_id=silver_snapshot_id,
        gold_snapshot_id=gold_snapshot_id,
        gold_skipped=not gold_written,
        keys_processed=outcome.keys_processed if outcome else 0,
        lower_versions_ignored=outcome.lower_versions_ignored if outcome else 0,
        ff14_conflicts=outcome.ff14_conflicts if outcome else 0,
        work_available=outcome.work_available if outcome else 0,
        work_in_flight=outcome.work_in_flight if outcome else 0,
        work_completed=outcome.work_completed if outcome else 0,
        files_planned=outcome.files_planned if outcome else 0,
        bytes_planned=outcome.bytes_planned if outcome else 0,
        files_removed=outcome.files_removed if outcome else 0,
        files_added=outcome.files_added if outcome else 0,
        bytes_removed=outcome.bytes_removed if outcome else 0,
        bytes_added=outcome.bytes_added if outcome else 0,
        snapshot_delta=outcome.snapshot_delta if outcome else 0,
    )

    if not SHADOW_COMPARE_ENABLED:
        shadow_state = "disabled"
    else:
        shadow_state = "skipped" if shadow_skipped else "compared"
    return CycleOutcome(
        cycle_id=cycle_id,
        gold="rebuilt" if gold_written else "skipped",
        shadow=shadow_state,
        duration_ms=cycle_duration_ms,
    )


def run(
    catalog: RestCatalog,
    metrics: Metrics,
    mode: str | None = None,
    *,
    cycle_id: str | None = None,
    fs: S3FileSystem | None = None,
) -> None:
    selected_mode = (mode or SILVER_MODE).lower()
    cycle_id = cycle_id or uuid.uuid4().hex
    if selected_mode not in {"b2", "legacy"}:
        raise ValueError(f"Unsupported SILVER_MODE: {selected_mode}")
    if (
        selected_mode == "legacy"
        and GOLD_SOURCE == "legacy"
        and not SHADOW_COMPARE_ENABLED
    ):
        cycle = _run_legacy(catalog, metrics, cycle_id=cycle_id)
    else:
        cycle = _run_m4(catalog, metrics, selected_mode, cycle_id=cycle_id, fs=fs)

    if cycle is None:
        # An early return or an abort. Staying silent is the signal.
        return
    # The one site that emits the liveness marker.  stdout, unconditional and
    # flushed: a liveness signal that can be switched off, buffered away or
    # mixed into stderr diagnostics is not a liveness signal.
    print(
        f"{CYCLE_COMPLETE_MARKER} cycle_id={cycle.cycle_id} gold={cycle.gold} "
        f"shadow={cycle.shadow} duration_ms={cycle.duration_ms}",
        flush=True,
    )


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
