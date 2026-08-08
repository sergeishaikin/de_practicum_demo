from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
from pyarrow.fs import S3FileSystem
from pyiceberg.catalog.rest import RestCatalog

from medallion import iceberg_medallion as m

REPO_ROOT = Path(__file__).resolve().parents[2]
ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:18181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:19000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minio")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")
BUCKET = "de-practicum"


def catalog() -> RestCatalog:
    return RestCatalog(
        "default",
        **{
            "uri": ICEBERG_CATALOG_URI,
            "warehouse": ICEBERG_WAREHOUSE,
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": "us-east-1",
            "s3.path-style-access": "true",
        },
    )


def storage() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region="us-east-1",
        scheme="http",
    )


def make_row(order_id: str, version: int, amount: float, event_day: date) -> dict:
    timestamp = datetime(event_day.year, event_day.month, event_day.day, 12)
    return {
        "order_id": order_id,
        "customer": f"{order_id}-v{version}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": timestamp,
        "kafka_timestamp": timestamp,
        "kafka_partition": 0,
        "kafka_offset": version,
        "event_date": event_day,
        "business_version": version,
    }


def append_work(table, load_id: str, rows: list[dict], fs: S3FileSystem, prefix: str) -> None:
    before = {item["file_path"] for item in table.inspect.data_files().to_pylist()}
    table.append(m._rows_to_silver(rows), snapshot_properties={"load-id": load_id})
    after = {item["file_path"] for item in table.inspect.data_files().to_pylist()}
    record = {
        "version": 1,
        "load_id": load_id,
        "source_paths": [f"m4/{load_id}.parquet"],
        "bronze_data_files": sorted(after - before),
        "row_count": len(rows),
    }
    with fs.open_output_stream(f"{BUCKET}/{prefix}/{load_id}.json") as output:
        output.write(json.dumps(record).encode("utf-8"))


def start_medallion(
    namespace: str,
    outbox_prefix: str,
    progress_path: str,
    *,
    gold_source: str,
    shadow: bool,
) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "ICEBERG_CATALOG_URI": ICEBERG_CATALOG_URI,
            "ICEBERG_WAREHOUSE": ICEBERG_WAREHOUSE,
            "BRONZE_NAMESPACE": namespace,
            "BRONZE_TABLE": "bronze",
            "SILVER_NAMESPACE": namespace,
            "SILVER_TABLE": "silver",
            "GOLD_NAMESPACE": namespace,
            "GOLD_TABLE": "gold",
            "MINIO_BUCKET": BUCKET,
            "S3_ENDPOINT": S3_ENDPOINT,
            "AWS_ACCESS_KEY_ID": ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
            "SILVER_MODE": "b2",
            "GOLD_SOURCE": gold_source,
            "SHADOW_COMPARE": "1" if shadow else "0",
            "BRONZE_OUTBOX_PREFIX": outbox_prefix,
            "MEDALLION_PROGRESS_PATH": progress_path,
            "MEDALLION_INTERVAL_SECONDS": "1",
            "METRICS_ENABLED": "0",
        }
    )
    return subprocess.Popen(
        [sys.executable, "iceberg/medallion/iceberg_medallion.py"],
        cwd=REPO_ROOT,
        env=env,
        stdout=None,
        stderr=None,
    )


def wait_for_completed(fs: S3FileSystem, progress_path: str, load_id: str) -> None:
    deadline = time.time() + 90
    object_path = f"{BUCKET}/{progress_path}"
    while time.time() < deadline:
        try:
            with fs.open_input_file(object_path) as source:
                progress = json.loads(source.read().decode("utf-8"))
            if load_id in progress.get("completed", {}):
                return
        except (FileNotFoundError, OSError):
            pass
        time.sleep(1)
    raise AssertionError(f"M4 work {load_id} did not complete")


def logical_rows(table) -> list[tuple]:
    rows = table.scan().to_arrow().to_pylist()
    return sorted(
        (
            row["order_id"],
            row["business_version"],
            row["customer"],
            row["amount"],
            row["event_date"],
        )
        for row in rows
    )


def logical_gold(table) -> list[tuple]:
    rows = table.scan().to_arrow().to_pylist()
    return sorted(
        (
            row["event_date"],
            row["country"],
            row["status"],
            row["orders_count"],
            row["total_amount"],
            row["avg_amount"],
            row["distinct_customers"],
        )
        for row in rows
    )


@pytest.mark.integration
def test_m4_persisted_silver_gold_shadow_and_rollback():
    run_id = uuid.uuid4().hex[:8]
    namespace = f"m4_{run_id}"
    outbox_prefix = f"m4/{run_id}/outbox"
    progress_path = f"m4/{run_id}/progress.json"
    cat = catalog()
    fs = storage()
    cat.create_namespace_if_not_exists(namespace)
    cat.create_table(
        f"{namespace}.bronze",
        schema=m.SILVER_SCHEMA,
        partition_spec=m.SILVER_PARTITION_SPEC,
    )
    bronze = cat.load_table(f"{namespace}.bronze")
    try:
        append_work(
            bronze,
            "001-seed",
            [
                make_row("a", 1, 10.0, date(2026, 1, 1)),
                make_row("b", 1, 20.0, date(2026, 1, 1)),
            ],
            fs,
            outbox_prefix,
        )
        append_work(
            bronze,
            "002-update",
            [
                make_row("a", 3, 30.0, date(2026, 1, 2)),
                make_row("a", 5, 50.0, date(2026, 1, 2)),
                make_row("b", 0, 20.0, date(2026, 1, 3)),
            ],
            fs,
            outbox_prefix,
        )

        proc = start_medallion(
            namespace,
            outbox_prefix,
            progress_path,
            gold_source="persisted_silver",
            shadow=True,
        )
        wait_for_completed(fs, progress_path, "002-update")
        proc.terminate()
        proc.wait(timeout=10)

        silver = cat.load_table(f"{namespace}.silver")
        gold = cat.load_table(f"{namespace}.gold")
        assert logical_rows(silver) == [
            ("a", 5, "a-v5", 50.0, date(2026, 1, 2)),
            ("b", 1, "b-v1", 20.0, date(2026, 1, 1)),
        ]
        assert gold.scan().to_arrow().num_rows == 2
        silver_snapshots = len(silver.metadata.snapshots)
        gold_rows = logical_gold(gold)

        append_work(
            bronze,
            "003-late",
            [make_row("a", 3, 30.0, date(2026, 1, 3))],
            fs,
            outbox_prefix,
        )
        proc = start_medallion(
            namespace,
            outbox_prefix,
            progress_path,
            gold_source="persisted_silver",
            shadow=True,
        )
        wait_for_completed(fs, progress_path, "003-late")
        proc.terminate()
        proc.wait(timeout=10)
        assert len(cat.load_table(f"{namespace}.silver").metadata.snapshots) == silver_snapshots

        # Roll back only the Gold source. B2 Silver remains authoritative and unchanged.
        proc = start_medallion(
            namespace,
            outbox_prefix,
            progress_path,
            gold_source="legacy",
            shadow=True,
        )
        time.sleep(3)
        proc.terminate()
        proc.wait(timeout=10)
        assert len(cat.load_table(f"{namespace}.silver").metadata.snapshots) == silver_snapshots
        assert logical_gold(cat.load_table(f"{namespace}.gold")) == gold_rows
    finally:
        for identifier in (
            f"{namespace}.gold",
            f"{namespace}.silver",
            f"{namespace}.bronze",
        ):
            try:
                cat.drop_table(identifier)
            except Exception:
                pass
        try:
            cat.drop_namespace(namespace)
        except Exception:
            pass
        try:
            fs.delete_dir(f"m4/{run_id}")
        except Exception:
            pass
