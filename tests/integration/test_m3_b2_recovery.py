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


def fs() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region="us-east-1",
        scheme="http",
    )


def append_work(table, load_id: str, rows: list[dict], storage: S3FileSystem, outbox_prefix: str) -> None:
    before = {
        item["file_path"] for item in table.inspect.data_files().to_pylist()
    }
    table.append(m._rows_to_silver(rows), snapshot_properties={"load-id": load_id})
    after = {item["file_path"] for item in table.inspect.data_files().to_pylist()}
    record = {
        "version": 1,
        "load_id": load_id,
        "source_paths": [f"m3/{load_id}.parquet"],
        "bronze_data_files": sorted(after - before),
        "row_count": len(rows),
    }
    with storage.open_output_stream(f"{BUCKET}/{outbox_prefix}/{load_id}.json") as output:
        output.write(json.dumps(record).encode("utf-8"))


def start_medallion(
    namespace: str,
    outbox_prefix: str,
    progress_path: str,
    *,
    crash_before: bool = False,
    crash_after: bool = False,
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
            "MINIO_BUCKET": BUCKET,
            "S3_ENDPOINT": S3_ENDPOINT,
            "AWS_ACCESS_KEY_ID": ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
            "SILVER_MODE": "b2",
            "BRONZE_OUTBOX_PREFIX": outbox_prefix,
            "MEDALLION_PROGRESS_PATH": progress_path,
            "MEDALLION_INTERVAL_SECONDS": "1",
            "METRICS_ENABLED": "0",
            "SIMULATE_B2_CRASH_BEFORE_COMMIT": "1" if crash_before else "0",
            "SIMULATE_B2_CRASH_AFTER_COMMIT": "1" if crash_after else "0",
        }
    )
    return subprocess.Popen(
        [sys.executable, "iceberg/medallion/iceberg_medallion.py"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_completed(storage: S3FileSystem, progress_path: str, load_id: str) -> dict:
    deadline = time.time() + 90
    object_path = f"{BUCKET}/{progress_path}"
    while time.time() < deadline:
        try:
            with storage.open_input_file(object_path) as source:
                progress = json.loads(source.read().decode("utf-8"))
            if load_id in progress.get("completed", {}):
                return progress
        except (FileNotFoundError, OSError):
            pass
        time.sleep(1)
    raise AssertionError(f"M3 work {load_id} did not complete")


def rows_by_id(table) -> dict[str, dict]:
    return {row["order_id"]: row for row in table.scan().to_arrow().to_pylist()}


def make_row(order_id: str, version: int, amount: float, event_day: date) -> dict:
    return {
        "order_id": order_id,
        "customer": f"{order_id}-v{version}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": datetime(event_day.year, event_day.month, event_day.day, 12),
        "kafka_timestamp": datetime(event_day.year, event_day.month, event_day.day, 12),
        "kafka_partition": 0,
        "kafka_offset": version,
        "event_date": event_day,
        "business_version": version,
    }


@pytest.mark.integration
def test_m3_b2_projection_and_crash_recovery():
    run_id = uuid.uuid4().hex[:8]
    namespace = f"m3_{run_id}"
    outbox_prefix = f"m3/{run_id}/outbox"
    progress_path = f"m3/{run_id}/progress.json"
    cat = catalog()
    storage = fs()
    cat.create_namespace_if_not_exists(namespace)
    cat.create_table(
        f"{namespace}.bronze",
        schema=m.SILVER_SCHEMA,
        partition_spec=m.SILVER_PARTITION_SPEC,
    )
    bronze = cat.load_table(f"{namespace}.bronze")
    try:
        seed_id = f"seed-{run_id}"
        append_work(
            bronze,
            seed_id,
            [
                make_row("a", 1, 10.0, date(2026, 1, 1)),
                make_row("b", 1, 20.0, date(2026, 1, 1)),
            ],
            storage,
            outbox_prefix,
        )
        proc = start_medallion(namespace, outbox_prefix, progress_path)
        wait_for_completed(storage, progress_path, seed_id)
        proc.terminate()
        proc.wait(timeout=10)

        update_id = f"update-{run_id}"
        append_work(
            bronze,
            update_id,
            [
                {
                    **rows_by_id(bronze)["a"],
                    "customer": "a-v3",
                    "amount": 30.0,
                    "status": "shipped",
                    "event_date": date(2026, 1, 2),
                    "business_version": 3,
                    "kafka_offset": 3,
                },
                {
                    **rows_by_id(bronze)["a"],
                    "customer": "a-v5",
                    "amount": 50.0,
                    "status": "delivered",
                    "event_date": date(2026, 1, 2),
                    "business_version": 5,
                    "kafka_offset": 4,
                },
                {
                    **rows_by_id(bronze)["b"],
                    "business_version": 1,
                    "kafka_offset": 99,
                },
            ],
            storage,
            outbox_prefix,
        )
        proc = start_medallion(namespace, outbox_prefix, progress_path)
        wait_for_completed(storage, progress_path, update_id)
        proc.terminate()
        proc.wait(timeout=10)

        silver = cat.load_table(f"{namespace}.silver")
        state = rows_by_id(silver)
        assert set(state) == {"a", "b"}
        assert state["a"]["business_version"] == 5
        assert state["a"]["customer"] == "a-v5"
        assert state["a"]["event_date"] == date(2026, 1, 2)
        assert state["b"]["business_version"] == 1
        snapshots_after_update = len(silver.metadata.snapshots)

        replay_id = f"replay-{run_id}"
        append_work(bronze, replay_id, [state["a"]], storage, outbox_prefix)
        proc = start_medallion(namespace, outbox_prefix, progress_path)
        wait_for_completed(storage, progress_path, replay_id)
        proc.terminate()
        proc.wait(timeout=10)
        assert len(cat.load_table(f"{namespace}.silver").metadata.snapshots) == snapshots_after_update

        before_id = f"before-{run_id}"
        append_work(bronze, before_id, [{**state["a"], "order_id": "before", "business_version": 1}], storage, outbox_prefix)
        proc = start_medallion(namespace, outbox_prefix, progress_path, crash_before=True)
        assert proc.wait(timeout=90) == 21
        proc = start_medallion(namespace, outbox_prefix, progress_path)
        wait_for_completed(storage, progress_path, before_id)
        proc.terminate()
        proc.wait(timeout=10)
        assert "before" in rows_by_id(cat.load_table(f"{namespace}.silver"))

        after_id = f"after-{run_id}"
        append_work(bronze, after_id, [{**state["a"], "order_id": "after", "business_version": 1}], storage, outbox_prefix)
        proc = start_medallion(namespace, outbox_prefix, progress_path, crash_after=True)
        assert proc.wait(timeout=90) == 22
        snapshots_after_commit = len(cat.load_table(f"{namespace}.silver").metadata.snapshots)
        proc = start_medallion(namespace, outbox_prefix, progress_path)
        wait_for_completed(storage, progress_path, after_id)
        proc.terminate()
        proc.wait(timeout=10)
        assert len(cat.load_table(f"{namespace}.silver").metadata.snapshots) == snapshots_after_commit
        assert len(rows_by_id(cat.load_table(f"{namespace}.silver"))) == 4
    finally:
        for identifier in (f"{namespace}.silver", f"{namespace}.bronze"):
            try:
                cat.drop_table(identifier)
            except Exception:
                pass
        try:
            cat.drop_namespace(namespace)
        except Exception:
            pass
        try:
            storage.delete_dir(f"m3/{run_id}")
        except Exception:
            pass
