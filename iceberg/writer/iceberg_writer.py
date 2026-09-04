from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyarrow as pa
import pyarrow.dataset as ds
from pyarrow.fs import FileInfo, FileSelector, S3FileSystem
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.exceptions import CommitFailedException, NoSuchTableError
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    IcebergType,
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from openlineage.client.event_v2 import RunState

from common import lineage
from common import provenance as prov
from common.ops import Metrics
from common.telemetry import setup_telemetry

CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://iceberg-rest:8181")
WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
NAMESPACE = os.getenv("ICEBERG_NAMESPACE", "bronze")
TABLE_NAME = os.getenv("ICEBERG_TABLE", "orders")
TABLE_IDENTIFIER = f"{NAMESPACE}.{TABLE_NAME}"

BUCKET = os.getenv("MINIO_BUCKET", "de-practicum")
LANDING_PREFIX = os.getenv("LANDING_PREFIX", "streaming/orders_raw")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
STATE_FILE = Path(os.getenv("STATE_FILE", "/state/ingested.json"))
MAX_APPEND_ATTEMPTS = int(os.getenv("MAX_APPEND_ATTEMPTS", "5"))
BRONZE_OUTBOX_PREFIX = os.getenv("BRONZE_OUTBOX_PREFIX", "streaming/bronze_outbox")

SIMULATE_CRASH_AFTER_COMMIT = os.getenv("SIMULATE_CRASH_AFTER_COMMIT", "0") == "1"
SIMULATE_CRASH_BEFORE_COMMIT = os.getenv("SIMULATE_CRASH_BEFORE_COMMIT", "0") == "1"

LOAD_ID_KEY = "load-id"

# The one edge this service performs: it reads Parquet the streaming job left in
# the landing prefix and appends it to Bronze. It never reads Kafka, so it never
# claims that edge - see `docs/LINEAGE.md`.
LINEAGE_JOB = "iceberg-writer.landing-to-bronze"
LANDING_DATASET = lineage.object_store_dataset(BUCKET, LANDING_PREFIX)
BRONZE_DATASET = lineage.iceberg_dataset(CATALOG_URI, TABLE_IDENTIFIER)

TABLE_SCHEMA = Schema(
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
    # New-baseline lineage is additive and optional so historical Landing
    # files remain appendable.  Values are copied by name from Parquet; no
    # Silver/Gold schema or deduplication authority is changed here.
    NestedField(12, "source_epoch_id", StringType(), required=False),
    NestedField(13, "event_id", StringType(), required=False),
    NestedField(14, "canonical_payload", StringType(), required=False),
    NestedField(15, "canonical_payload_hash", StringType(), required=False),
)

BRONZE_LINEAGE_FIELDS = (
    ("source_epoch_id", StringType()),
    ("event_id", StringType()),
    ("canonical_payload", StringType()),
    ("canonical_payload_hash", StringType()),
)

PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=10,
        field_id=1000,
        transform=DayTransform(),
        name="event_date_day",
    )
)


def load_state() -> tuple[set[str], dict[str, list[str]]]:
    if not STATE_FILE.exists():
        return set(), {}
    raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return set(raw), {}
    return set(raw.get("done", [])), {
        load_id: list(paths) for load_id, paths in raw.get("pending", {}).items()
    }


def save_state(done: set[str], pending: dict[str, list[str]]) -> None:
    """Persist writer progress without exposing a partially-written state file."""

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_name(f".{STATE_FILE.name}.{uuid.uuid4().hex}.tmp")
    payload = {
        "done": sorted(done),
        "pending": {load_id: paths for load_id, paths in pending.items()},
    }
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STATE_FILE)
    finally:
        if temporary.exists():
            temporary.unlink()


def _storage_path(path: str) -> str:
    parsed = urlparse(path)
    if parsed.scheme in {"s3", "s3a", "s3n"}:
        return f"{parsed.netloc}/{parsed.path.lstrip('/')}"
    if parsed.scheme:
        raise ValueError(f"Unsupported storage path scheme: {parsed.scheme}")
    if path.startswith(f"{BUCKET}/"):
        return path
    return f"{BUCKET}/{path.lstrip('/')}"


def outbox_object_path(load_id: str) -> str:
    return f"{BUCKET}/{BRONZE_OUTBOX_PREFIX}/{load_id}.json"


def table_data_files(table) -> set[str]:
    """Return live Bronze data files, tolerating lightweight test doubles."""

    try:
        return {item["file_path"] for item in table.inspect.data_files().to_pylist()}
    except (AttributeError, TypeError):
        return set()


def publish_outbox(
    fs: S3FileSystem,
    load_id: str,
    source_paths: list[str],
    bronze_data_files: list[str],
    row_count: int,
) -> None:
    """Publish one committed Bronze work item as an atomic object PUT."""

    payload: dict[str, Any] = {
        "version": 1,
        "load_id": load_id,
        "source_paths": sorted(source_paths),
        "bronze_data_files": sorted(_storage_path(path) for path in bronze_data_files),
        "row_count": row_count,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    with fs.open_output_stream(outbox_object_path(load_id)) as out:
        out.write(raw)


def get_fs() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region=S3_REGION,
        scheme="http",
    )


SPARK_METADATA_DIR = "_spark_metadata"


def _normalize_spark_path(path: str) -> str:
    """Convert Spark's URI form to the S3FileSystem bucket/key form."""

    parsed = urlparse(path)
    if parsed.scheme in {"s3", "s3a", "s3n"}:
        return f"{parsed.netloc}/{parsed.path.lstrip('/')}"
    if parsed.scheme:
        raise ValueError(f"Unsupported Spark commit path scheme: {parsed.scheme}")
    if path.startswith(f"{BUCKET}/"):
        return path
    return f"{BUCKET}/{path.lstrip('/')}"


def _read_spark_commit_log(fs: S3FileSystem, path: str) -> set[str]:
    """Read one Spark FileStreamSink metadata log and return added files."""

    # Sequential, not random access: `open_input_file` sizes itself from a HEAD
    # taken at open and returns that many bytes even when the body since became
    # shorter, exposing uninitialised memory as the tail. See _read_json in the
    # medallion for the captured evidence.
    with fs.open_input_stream(path) as source:
        raw = source.read().decode("utf-8")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines or lines[0] != "v1":
        raise ValueError(f"Unsupported or invalid Spark commit log: {path}")

    committed: set[str] = set()
    for line in lines[1:]:
        entry = json.loads(line)
        if entry.get("action") != "add":
            continue
        raw_file_path = entry.get("path")
        if not isinstance(raw_file_path, str):
            raise ValueError(f"Spark commit entry has no path: {path}")
        committed.add(_normalize_spark_path(raw_file_path))
    return committed


def committed_landing_paths(fs: S3FileSystem) -> set[str]:
    """Return files represented by Spark's committed file-sink metadata."""

    metadata_base = f"{BUCKET}/{LANDING_PREFIX}/{SPARK_METADATA_DIR}"
    selector = FileSelector(
        base_dir=metadata_base,
        recursive=True,
        allow_not_found=True,
    )
    metadata_files = [
        info
        for info in fs.get_file_info(selector)
        if info.is_file and not info.path.endswith(".crc")
    ]
    committed: set[str] = set()
    for info in sorted(metadata_files, key=lambda item: item.path):
        committed.update(_read_spark_commit_log(fs, info.path))
    return committed


def list_new_files(fs: S3FileSystem, done: set[str]) -> list[FileInfo]:
    base = f"{BUCKET}/{LANDING_PREFIX}"
    selector = FileSelector(
        base_dir=base,
        recursive=True,
        allow_not_found=True,
    )
    infos = fs.get_file_info(selector)
    committed = committed_landing_paths(fs)

    new_files = []
    for info in infos:
        if not info.is_file:
            continue
        if not info.path.endswith(".parquet"):
            continue
        if info.path in done:
            continue
        if info.path not in committed:
            continue
        new_files.append(info)

    new_files.sort(key=lambda info: info.path)
    return new_files


def read_batch(fs: S3FileSystem, files: list[FileInfo]) -> pa.Table:
    paths = [info.path for info in files]
    hive_partitioning = ds.partitioning(
        pa.schema([pa.field("event_date", pa.date32())]),
        flavor="hive",
    )
    dataset = ds.dataset(
        paths,
        format="parquet",
        filesystem=fs,
        partitioning=hive_partitioning,
    )
    arrow_table = dataset.to_table()
    target_types = [
        pa.timestamp("us", tz=None) if pa.types.is_timestamp(f.type) else f.type
        for f in arrow_table.schema
    ]
    return arrow_table.cast(
        pa.schema(
            [
                (f.name, target_type)
                for f, target_type in zip(arrow_table.schema, target_types, strict=True)
            ]
        )
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


def ensure_table(catalog: RestCatalog) -> None:
    catalog.create_namespace_if_not_exists(NAMESPACE)
    try:
        table = catalog.load_table(TABLE_IDENTIFIER)
    except NoSuchTableError:
        catalog.create_table(
            identifier=TABLE_IDENTIFIER,
            schema=TABLE_SCHEMA,
            partition_spec=PARTITION_SPEC,
        )
        return

    # M1/new-baseline evolution is additive: a Bronze table created before the
    # contract can be upgraded without rewriting its existing data files.
    schema_fn = getattr(table, "schema", None)
    update_schema_fn = getattr(table, "update_schema", None)
    if schema_fn is None or update_schema_fn is None:
        return
    existing_columns = set(schema_fn().column_names)
    update = update_schema_fn()
    missing: list[tuple[str, IcebergType, str]] = []
    if "business_version" not in existing_columns:
        missing.append(
            (
                "business_version",
                LongType(),
                "Domain ordering; Kafka offset is transport metadata only",
            )
        )
    # Keep compatibility with very old lightweight table doubles that model
    # only the M1 business_version migration; real Bronze tables that already
    # have business_version receive all four new optional fields.
    elif existing_columns:
        missing.extend(
            (name, field_type, "New-baseline canonical event lineage")
            for name, field_type in BRONZE_LINEAGE_FIELDS
            if name not in existing_columns
        )
    for name, field_type, doc in missing:
        update.add_column(name, field_type, doc=doc)
    if missing:
        update.commit()


def committed_load_records(catalog: RestCatalog) -> dict[str, dict[str, Any]]:
    try:
        table = catalog.load_table(TABLE_IDENTIFIER)
    except NoSuchTableError:
        return {}
    committed: dict[str, dict[str, Any]] = {}
    for snapshot in table.metadata.snapshots:
        if snapshot.summary:
            load_id = snapshot.summary.additional_properties.get(LOAD_ID_KEY)
            if load_id:
                data_files: list[str] = []
                try:
                    entries = table.inspect.entries(snapshot_id=snapshot.snapshot_id)
                    data_files = sorted(
                        entry["data_file"]["file_path"]
                        for entry in entries.to_pylist()
                        if entry["status"] == 1 and entry["data_file"]["content"] == 0
                    )
                except Exception:
                    # Snapshot-summary recovery must remain usable if metadata
                    # inspection is unavailable; the old idempotency signal is
                    # still valid, and the next writer cycle can retry publishing.
                    pass
                committed[load_id] = {
                    "snapshot_id": getattr(snapshot, "snapshot_id", None),
                    "bronze_data_files": data_files,
                }
    return committed


def snapshot_for_load(table, load_id: str) -> int | None:
    """The snapshot this load's append produced.

    Scans metadata already in memory rather than re-inspecting the table, so
    naming the snapshot on the lineage event costs no extra catalog I/O. The
    `load-id` summary stamp is the join, exactly as in the provenance receipt.
    """
    for snapshot in getattr(table.metadata, "snapshots", []) or []:
        summary = getattr(snapshot, "summary", None)
        if summary and summary.additional_properties.get(LOAD_ID_KEY) == load_id:
            return getattr(snapshot, "snapshot_id", None)
    return None


def committed_load_ids(catalog: RestCatalog) -> set[str]:
    """Compatibility view used by existing writer callers and tests."""

    return set(committed_load_records(catalog))


def recover_pending(
    done: set[str],
    pending: dict[str, list[str]],
    catalog: RestCatalog,
    fs: S3FileSystem | None = None,
) -> None:
    if not pending:
        return
    committed = committed_load_records(catalog)
    for load_id in list(pending):
        paths = pending[load_id]
        if load_id in committed:
            if fs is not None:
                publish_outbox(
                    fs,
                    load_id,
                    paths,
                    committed[load_id]["bronze_data_files"],
                    row_count=0,
                )
            done.update(paths)
            del pending[load_id]
            print(
                f"Recovery: load {load_id[:8]} already committed "
                f"({len(paths)} files) -> marked done, no re-append",
                flush=True,
            )
        else:
            print(
                f"Recovery: load {load_id[:8]} NOT committed "
                f"({len(paths)} files) -> will re-append",
                flush=True,
            )
    save_state(done, pending)


def emit_ingest_lineage(emitter: lineage.LineageEmitter, load_id: str, table) -> bool:
    """Record the landing-to-Bronze edge this append performed.

    Declares the two identifiers this boundary genuinely lacks rather than
    filling them: the writer is a long-running service, so no Airflow run
    launched this work, and no tracing backend exists until NG-0.4.
    """
    values: dict[str, object] = {
        prov.LOAD_ID: load_id,
        prov.ICEBERG_TABLE: TABLE_IDENTIFIER,
    }
    unknown = {
        prov.DAG_RUN_ID: "the writer is a continuous service, not an Airflow task",
        prov.TRACE_ID: "no tracing backend exists yet; NG-0.4 introduces one",
    }
    try:
        snapshot_id = snapshot_for_load(table, load_id)
    except Exception as exc:
        print(
            f"Lineage snapshot read failed ({TABLE_IDENTIFIER}): "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        snapshot_id = None
    if snapshot_id is not None:
        values[prov.ICEBERG_SNAPSHOT_ID] = snapshot_id
    else:
        unknown[prov.ICEBERG_SNAPSHOT_ID] = (
            "the snapshot carrying this load-id could not be read back"
        )
    envelope = prov.ProvenanceEnvelope(values=values, unknown=unknown)
    return emitter.emit(
        run_id=lineage.run_id_for(load_id),
        event_type=RunState.COMPLETE,
        inputs=[LANDING_DATASET],
        outputs=[BRONZE_DATASET],
        envelope=envelope,
    )


def main() -> None:
    print(f"Iceberg writer started: {TABLE_IDENTIFIER}", flush=True)
    print(f"Watching s3://{BUCKET}/{LANDING_PREFIX}", flush=True)

    done, pending = load_state()
    fs = get_fs()
    catalog = get_catalog()
    metrics = Metrics()
    telemetry = setup_telemetry("iceberg-writer")
    lineage.register_edge_owner(BRONZE_DATASET, LINEAGE_JOB)
    emitter = lineage.LineageEmitter(LINEAGE_JOB)

    recover_pending(done, pending, catalog, fs)

    while True:
        load_id = None
        try:
            new_files = list_new_files(fs, done)
            if new_files:
                load_id = uuid.uuid4().hex
                paths = [info.path for info in new_files]

                pending[load_id] = paths
                save_state(done, pending)

                if SIMULATE_CRASH_BEFORE_COMMIT:
                    print(
                        f"SIMULATED CRASH before commit (load {load_id[:8]})",
                        flush=True,
                    )
                    os._exit(2)

                with telemetry.span(
                    "writer.ingest",
                    {"lakehouse.files": len(new_files)},
                ):
                    arrow_table = read_batch(fs, new_files)
                ensure_table(catalog)
                table = catalog.load_table(TABLE_IDENTIFIER)
                before_data_files = table_data_files(table)
                started = time.monotonic()
                with telemetry.span("writer.bronze_append") as append_span:
                    for attempt in range(1, MAX_APPEND_ATTEMPTS + 1):
                        try:
                            table.append(
                                arrow_table,
                                snapshot_properties={LOAD_ID_KEY: load_id},
                            )
                            break
                        except CommitFailedException as exc:
                            if attempt == MAX_APPEND_ATTEMPTS:
                                raise
                            append_span.set_attribute("lakehouse.retry", attempt)
                            print(
                                f"Commit conflict (attempt {attempt}/{MAX_APPEND_ATTEMPTS}): "
                                f"{exc}; reloading table and retrying",
                                flush=True,
                            )
                            time.sleep(1)
                            table = catalog.load_table(TABLE_IDENTIFIER)
                duration_ms = int((time.monotonic() - started) * 1000)

                after_data_files = table_data_files(table)
                publish_outbox(
                    fs,
                    load_id,
                    paths,
                    sorted(after_data_files - before_data_files),
                    arrow_table.num_rows,
                )

                if SIMULATE_CRASH_AFTER_COMMIT:
                    print(
                        f"SIMULATED CRASH after commit (load {load_id[:8]})",
                        flush=True,
                    )
                    os._exit(3)

                del pending[load_id]
                done.update(paths)
                save_state(done, pending)
                print(
                    f"Ingested {arrow_table.num_rows} rows "
                    f"from {len(new_files)} new files (load {load_id[:8]})",
                    flush=True,
                )
                telemetry.log(
                    "writer ingest completed",
                    attributes={"lakehouse.rows": arrow_table.num_rows},
                )
                # Keep a real sampled OTel context active for the existing
                # duration observation so the exemplar points at this trace.
                with telemetry.span("writer.metrics", {"lakehouse.load_id": load_id}):
                    metrics.record(
                        source="writer",
                        status="success",
                        load_id=load_id,
                        rows_processed=arrow_table.num_rows,
                        files_processed=len(new_files),
                        duration_ms=duration_ms,
                    )
                emit_ingest_lineage(emitter, load_id, table)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Ingestion error: {exc}", file=sys.stderr, flush=True)
            telemetry.log("writer ingest failed")
            if load_id is not None and load_id in pending:
                committed = committed_load_records(catalog)
                if load_id in committed:
                    publish_outbox(
                        fs,
                        load_id,
                        pending[load_id],
                        committed[load_id]["bronze_data_files"],
                        row_count=0,
                    )
                    done.update(pending[load_id])
                file_count = len(pending[load_id])
                del pending[load_id]
                save_state(done, pending)
                with telemetry.span("writer.metrics", {"lakehouse.load_id": load_id}):
                    metrics.record(
                        source="writer",
                        status="error",
                        load_id=load_id,
                        files_processed=file_count,
                    )
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()  # pragma: no cover
