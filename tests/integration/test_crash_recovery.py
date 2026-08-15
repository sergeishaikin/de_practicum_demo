from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pyarrow.fs import FileSelector, S3FileSystem
from pyiceberg.catalog.rest import RestCatalog

REPO_ROOT = Path(__file__).resolve().parents[2]

ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:18181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:19000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minio")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")
BUCKET = "de-practicum"


def _catalog() -> RestCatalog:
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


def _fs() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region="us-east-1",
        scheme="http",
    )


def _orders_table(n: int) -> pa.Table:
    ts = datetime(2026, 1, 1, 12, 0, 0)
    return pa.table(
        {
            "order_id": [f"crash-{i}" for i in range(n)],
            "customer": [f"cust{i}" for i in range(n)],
            "amount": pa.array([10.0 * (i + 1) for i in range(n)], type=pa.float64()),
            "country": ["US"] * n,
            "status": ["paid"] * n,
            "event_time": [ts] * n,
            "kafka_timestamp": [ts] * n,
            "kafka_partition": pa.array(list(range(n)), type=pa.int32()),
            "kafka_offset": pa.array(list(range(n)), type=pa.int64()),
            "event_date": [date(2026, 1, 1)] * n,
            "business_version": pa.array([1] * n, type=pa.int64()),
        }
    )


def _start_writer(
    namespace: str,
    table: str,
    landing_prefix: str,
    state_file: Path,
    crash_mode: str | None,
) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "ICEBERG_CATALOG_URI": ICEBERG_CATALOG_URI,
            "ICEBERG_WAREHOUSE": ICEBERG_WAREHOUSE,
            "ICEBERG_NAMESPACE": namespace,
            "ICEBERG_TABLE": table,
            "MINIO_BUCKET": BUCKET,
            "LANDING_PREFIX": landing_prefix,
            "S3_ENDPOINT": S3_ENDPOINT,
            "AWS_ACCESS_KEY_ID": ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
            "STATE_FILE": str(state_file),
            "BRONZE_OUTBOX_PREFIX": f"{landing_prefix}/outbox",
            "POLL_INTERVAL_SECONDS": "1",
            "METRICS_ENABLED": "0",
            "SIMULATE_CRASH_BEFORE_COMMIT": "1" if crash_mode == "before" else "0",
            "SIMULATE_CRASH_AFTER_COMMIT": "1" if crash_mode == "after" else "0",
        }
    )
    return subprocess.Popen(
        [sys.executable, "iceberg/writer/iceberg_writer.py"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _landing_path(landing_prefix: str, filename: str) -> str:
    return f"{BUCKET}/{landing_prefix}/{filename}"


def _mark_spark_committed(fs: S3FileSystem, landing_prefix: str, filename: str) -> None:
    metadata_path = _landing_path(landing_prefix, "_spark_metadata/0")
    source_path = f"s3a://{_landing_path(landing_prefix, filename)}"
    payload = "v1\n" + json.dumps({"path": source_path, "action": "add"}) + "\n"
    with fs.open_output_stream(metadata_path) as out:
        out.write(payload.encode("utf-8"))


def _outbox_files(fs: S3FileSystem, landing_prefix: str) -> list[str]:
    selector = FileSelector(
        base_dir=_landing_path(landing_prefix, "outbox"),
        recursive=True,
        allow_not_found=True,
    )
    return [info.path for info in fs.get_file_info(selector) if info.is_file]


def _snapshot_count_and_rows(
    namespace: str, table: str, cat: RestCatalog
) -> tuple[int, int]:
    ice = cat.load_table(f"{namespace}.{table}")
    snapshots = list(ice.metadata.snapshots)
    return len(snapshots), ice.scan().to_arrow().num_rows


def _snapshot_business_versions(
    namespace: str, table: str, cat: RestCatalog
) -> list[int]:
    ice = cat.load_table(f"{namespace}.{table}")
    return ice.scan().to_arrow()["business_version"].to_pylist()


@pytest.fixture
def isolated_lake(tmp_path):
    run_id = uuid.uuid4().hex[:8]
    namespace = f"test_{run_id}"
    landing = f"test-crash/{run_id}"
    state_file = tmp_path / "state.json"
    yield namespace, "orders", landing, state_file
    cat = _catalog()
    fs = _fs()
    for ident in (f"{namespace}.orders",):
        try:
            cat.drop_table(ident)
        except Exception:
            pass
    try:
        cat.drop_namespace(namespace)
    except Exception:
        pass
    try:
        fs.delete_dir(landing)
    except Exception:
        pass


@pytest.mark.integration
def test_crash_after_commit_no_duplicate_append(isolated_lake):
    namespace, table, landing, state_file = isolated_lake
    fs = _fs()
    path = _landing_path(landing, "part-00000.parquet")
    with fs.open_output_stream(path) as out:
        pq.write_table(_orders_table(5), out)
    _mark_spark_committed(fs, landing, "part-00000.parquet")

    proc = _start_writer(namespace, table, landing, state_file, "after")
    assert proc.wait(timeout=90) == 3

    cat = _catalog()
    count, rows = _snapshot_count_and_rows(namespace, table, cat)
    assert count == 1
    assert rows == 5
    assert _snapshot_business_versions(namespace, table, cat) == [1] * 5
    assert len(_outbox_files(fs, landing)) == 1

    proc2 = _start_writer(namespace, table, landing, state_file, None)
    time.sleep(8)
    proc2.terminate()
    proc2.wait(timeout=10)

    count2, rows2 = _snapshot_count_and_rows(namespace, table, cat)
    assert count2 == 1
    assert rows2 == 5
    assert _snapshot_business_versions(namespace, table, cat) == [1] * 5
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["pending"] == {}
    assert path in state["done"]
    assert len(_outbox_files(fs, landing)) == 1


@pytest.mark.integration
def test_crash_before_commit_reappends_exactly_once(isolated_lake):
    namespace, table, landing, state_file = isolated_lake
    fs = _fs()
    path = _landing_path(landing, "part-00000.parquet")
    with fs.open_output_stream(path) as out:
        pq.write_table(_orders_table(5), out)
    _mark_spark_committed(fs, landing, "part-00000.parquet")

    proc = _start_writer(namespace, table, landing, state_file, "before")
    assert proc.wait(timeout=90) == 2

    proc2 = _start_writer(namespace, table, landing, state_file, None)
    deadline = time.time() + 90
    count = rows = 0
    while time.time() < deadline:
        try:
            count, rows = _snapshot_count_and_rows(namespace, table, cat := _catalog())
            if count >= 1:
                break
        except Exception:
            pass
        time.sleep(2)
    proc2.terminate()
    proc2.wait(timeout=10)

    assert count == 1
    assert rows == 5
    assert _snapshot_business_versions(namespace, table, _catalog()) == [1] * 5
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert path in state["done"]
    assert len(_outbox_files(fs, landing)) == 1
