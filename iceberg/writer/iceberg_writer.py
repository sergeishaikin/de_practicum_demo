from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from common.ops import Metrics

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
SETTLE_SECONDS = int(os.getenv("SETTLE_SECONDS", "5"))
STATE_FILE = Path(os.getenv("STATE_FILE", "/state/ingested.json"))
MAX_APPEND_ATTEMPTS = int(os.getenv("MAX_APPEND_ATTEMPTS", "5"))

SIMULATE_CRASH_AFTER_COMMIT = os.getenv("SIMULATE_CRASH_AFTER_COMMIT", "0") == "1"
SIMULATE_CRASH_BEFORE_COMMIT = os.getenv("SIMULATE_CRASH_BEFORE_COMMIT", "0") == "1"

LOAD_ID_KEY = "load-id"

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
    STATE_FILE.write_text(
        json.dumps(
            {
                "done": sorted(done),
                "pending": {load_id: paths for load_id, paths in pending.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def get_fs() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region=S3_REGION,
        scheme="http",
    )


def is_settled(info: FileInfo) -> bool:
    mtime = info.mtime
    if mtime.tzinfo is None:
        mtime = mtime.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - mtime >= timedelta(seconds=SETTLE_SECONDS)


def list_new_files(fs: S3FileSystem, done: set[str]) -> list[FileInfo]:
    base = f"{BUCKET}/{LANDING_PREFIX}"
    selector = FileSelector(
        base_dir=base,
        recursive=True,
        allow_not_found=True,
    )
    infos = fs.get_file_info(selector)

    new_files = []
    for info in infos:
        if not info.is_file:
            continue
        if not info.path.endswith(".parquet"):
            continue
        if "/_temporary/" in info.path:
            continue
        if info.path in done:
            continue
        if not is_settled(info):
            continue
        new_files.append(info)

    new_files.sort(key=lambda i: i.mtime)
    return new_files


def read_batch(fs: S3FileSystem, files: list[FileInfo]) -> object:
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
        catalog.load_table(TABLE_IDENTIFIER)
    except NoSuchTableError:
        catalog.create_table(
            identifier=TABLE_IDENTIFIER,
            schema=TABLE_SCHEMA,
            partition_spec=PARTITION_SPEC,
        )


def committed_load_ids(catalog: RestCatalog) -> set[str]:
    try:
        table = catalog.load_table(TABLE_IDENTIFIER)
    except NoSuchTableError:
        return set()
    committed = set()
    for snapshot in table.metadata.snapshots:
        if snapshot.summary:
            load_id = snapshot.summary.additional_properties.get(LOAD_ID_KEY)
            if load_id:
                committed.add(load_id)
    return committed


def recover_pending(
    done: set[str], pending: dict[str, list[str]], catalog: RestCatalog
) -> None:
    if not pending:
        return
    committed = committed_load_ids(catalog)
    for load_id in list(pending):
        paths = pending[load_id]
        if load_id in committed:
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


def main() -> None:
    print(f"Iceberg writer started: {TABLE_IDENTIFIER}", flush=True)
    print(f"Watching s3://{BUCKET}/{LANDING_PREFIX}", flush=True)

    done, pending = load_state()
    fs = get_fs()
    catalog = get_catalog()
    metrics = Metrics()

    recover_pending(done, pending, catalog)

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

                arrow_table = read_batch(fs, new_files)
                ensure_table(catalog)
                table = catalog.load_table(TABLE_IDENTIFIER)
                started = time.monotonic()
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
                        print(
                            f"Commit conflict (attempt {attempt}/{MAX_APPEND_ATTEMPTS}): "
                            f"{exc}; reloading table and retrying",
                            flush=True,
                        )
                        time.sleep(1)
                        table = catalog.load_table(TABLE_IDENTIFIER)
                duration_ms = int((time.monotonic() - started) * 1000)

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
                metrics.record(
                    source="writer",
                    status="success",
                    load_id=load_id,
                    rows_processed=arrow_table.num_rows,
                    files_processed=len(new_files),
                    duration_ms=duration_ms,
                )
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Ingestion error: {exc}", file=sys.stderr, flush=True)
            if load_id is not None and load_id in pending:
                committed = committed_load_ids(catalog)
                if load_id in committed:
                    done.update(pending[load_id])
                file_count = len(pending[load_id])
                del pending[load_id]
                save_state(done, pending)
                metrics.record(
                    source="writer",
                    status="error",
                    load_id=load_id,
                    files_processed=file_count,
                )
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()  # pragma: no cover
