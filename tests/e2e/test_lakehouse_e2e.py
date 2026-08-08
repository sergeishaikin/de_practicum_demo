"""Deterministic end-to-end test of the real-time lakehouse pipeline.

Publishes a fixed 101-event fixture to a dedicated Kafka topic and drives the
real chain end-to-end:

    fixture -> Kafka -> Spark 4.2 streaming -> landing parquet
             -> Iceberg writer -> bronze -> silver -> gold
             -> Trino -> Postgres metrics

Every run is isolated through a dedicated Kafka topic, landing prefix,
Iceberg namespace and the dedicated ``e2e`` Postgres database, so exact counts
and totals can be asserted without interference from the always-on random
producer (`orders-producer`). The streaming sink *and* the writer/medallion
``marts.lakehouse_metrics`` rows all land in ``e2e``; the canonical ``dwh``
database is asserted to gain neither fixture orders nor fixture metrics.

Medallion metrics carry no load-id, so the metrics assertion is additionally
scoped by a Postgres-side ``now()`` watermark taken just before the medallion
starts - without it, rows left by an earlier run would satisfy the check.

On failure the temp directory is preserved under ``artifacts/e2e-logs/<run_id>``
as a self-contained bundle (traceback, helper logs, streaming container log,
writer state, ``docker ps``, Trino schemas) and uploaded by the nightly
workflow.

Platform maintenance (``lakehouse_maintenance`` DAG) is verified separately by
``scripts/verify_maintenance_dag.py``, which the nightly workflow runs as its
own step; it is not part of the deterministic E2E chain.

Requires the full stack::

    docker compose -f docker-compose.yml -f docker-compose.extended.yml up -d --build

Marked ``e2e`` and excluded from the fast suite via pytest.ini.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import pytest
from pyarrow.dataset import dataset as arrow_dataset
from pyarrow.fs import S3FileSystem
from pyiceberg.catalog.rest import RestCatalog

REPO_ROOT = Path(__file__).resolve().parents[2]

ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:18181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:19000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minio")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")
BUCKET = "de-practicum"

PG = {
    "host": os.getenv("DWH_HOST", "localhost"),
    "port": int(os.getenv("DWH_PORT", "15432")),
    "dbname": os.getenv("DWH_DB", "dwh"),
    "user": os.getenv("DWH_USER", "app"),
    "password": os.getenv("DWH_PASSWORD", "app"),
}

VALID_STATUSES = {"created", "paid", "shipped", "delivered"}
FIXTURE_DATE = "2026-08-07"
FIXTURE_TS = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc).isoformat()

STREAMING_CONTAINER = "de-demo-orders-streaming"
TRINO_CONTAINER = "de-demo-trino"
KAFKA_CONTAINER = "de-demo-kafka"
KAFKA_BOOTSTRAP = "localhost:9092"
E2E_DB = "e2e"
E2E_PG = {**PG, "dbname": E2E_DB}
IVY_CACHE_VOLUME = "de_demo_spark_ivy_cache"
REQUIRED_CONTAINERS = (
    "de-demo-kafka",
    "de-demo-minio",
    "de-demo-trino",
    "de-demo-iceberg-rest",
    "de-demo-orders-streaming",
    "de-demo-postgres",
)


# --------------------------------------------------------------------------- #
# Fixture: exactly 100 deterministic events with known structural expectations
# --------------------------------------------------------------------------- #
def build_fixture() -> list[dict]:
    events: list[dict] = []

    countries = ["UK", "US", "ES"]
    statuses = ["paid", "created"]
    customers = ["alice", "bob", "carol"]
    for i in range(85):
        events.append(
            {
                "order_id": f"clean-{i:03d}",
                "customer": customers[i % 3],
                "amount": float((i % 9) + 1),
                "country": countries[i % 3],
                "status": statuses[i % 2],
                "event_time": FIXTURE_TS,
            }
        )

    for dup in ("dup-1", "dup-2", "dup-3"):
        events.append(
            {
                "order_id": dup,
                "customer": "dave",
                "amount": 10.0,
                "country": "UK",
                "status": "paid",
                "business_version": 1,
                "event_time": FIXTURE_TS,
            }
        )
        events.append(
            {
                "order_id": dup,
                "customer": "erin",
                "amount": 30.0,
                "country": "UK",
                "status": "delivered",
                "business_version": 5,
                "event_time": FIXTURE_TS,
            }
        )
        if dup == "dup-1":
            events.append(
                {
                    "order_id": dup,
                    "customer": "frank",
                    "amount": 20.0,
                    "country": "UK",
                    "status": "shipped",
                    "business_version": 3,
                    "event_time": FIXTURE_TS,
                }
            )

    events.append(
        {
            "order_id": "bad-status-1",
            "customer": "frank",
            "amount": 40.0,
            "country": "US",
            "status": "cancelled",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": "bad-status-2",
            "customer": "grace",
            "amount": 41.0,
            "country": "US",
            "status": "cancelled",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": "neg-amount-1",
            "customer": "heidi",
            "amount": -5.0,
            "country": "ES",
            "status": "paid",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": "neg-amount-2",
            "customer": "ivan",
            "amount": -10.0,
            "country": "ES",
            "status": "paid",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": "null-amount",
            "customer": "judy",
            "amount": None,
            "country": "FR",
            "status": "paid",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": "null-country",
            "customer": "ken",
            "amount": 50.0,
            "country": None,
            "status": "paid",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": "null-event-time",
            "customer": "leo",
            "amount": 51.0,
            "country": "US",
            "status": "paid",
            "event_time": None,
        }
    )

    events.append(
        {
            "order_id": None,
            "customer": "mia",
            "amount": 60.0,
            "country": "US",
            "status": "paid",
            "event_time": FIXTURE_TS,
        }
    )
    events.append(
        {
            "order_id": None,
            "customer": "nina",
            "amount": 61.0,
            "country": "US",
            "status": "paid",
            "event_time": FIXTURE_TS,
        }
    )

    for event in events:
        event.setdefault("business_version", 1)

    return events


def expected_pipeline(fixture: list[dict]) -> dict:
    landed = [e for e in fixture if e["order_id"] is not None]
    latest: dict[str, dict] = {}
    for event in landed:
        current = latest.get(event["order_id"])
        if current is None or event["business_version"] > current["business_version"]:
            latest[event["order_id"]] = event
    silver_rows = list(latest.values())

    violations = {
        "status_invalid": sum(1 for e in landed if e["status"] not in VALID_STATUSES),
        "amount_null_or_nonpositive": sum(
            1 for e in landed if e["amount"] is None or e["amount"] <= 0
        ),
        "country_null": sum(1 for e in landed if e["country"] is None),
        "event_time_null": sum(1 for e in landed if e["event_time"] is None),
    }

    groups: dict[tuple, dict] = {}
    for e in silver_rows:
        event_date = e["event_time"].split("T")[0] if e["event_time"] else None
        key = (event_date, e["country"], e["status"])
        group = groups.setdefault(
            key, {"orders_count": 0, "total": 0.0, "customers": set()}
        )
        group["orders_count"] += 1
        if e["amount"] is not None:
            group["total"] += e["amount"]
        if e["customer"] is not None:
            group["customers"].add(e["customer"])

    return {
        "total_events": len(fixture),
        "landing_rows": len(landed),
        "bronze_rows": len(landed),
        "silver_rows": len(silver_rows),
        "duplicates_removed": len(landed) - len(silver_rows),
        "violations": violations,
        "total_violations": sum(violations.values()),
        "gold_groups": groups,
        "gold_row_count": len(groups),
        "total_revenue": sum(g["total"] for g in groups.values()),
        "uk_delivered_total": groups[(FIXTURE_DATE, "UK", "delivered")]["total"],
        "uk_paid_total": groups[(FIXTURE_DATE, "UK", "paid")]["total"],
        "cancelled_count": groups[(FIXTURE_DATE, "US", "cancelled")]["orders_count"],
        "business_version_counts": dict(
            Counter(event["business_version"] for event in landed)
        ),
    }


# --------------------------------------------------------------------------- #
# Docker helpers
# --------------------------------------------------------------------------- #
def docker(*args: str, input_text: str | None = None, timeout: int = 120) -> str:
    proc = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def kafka_tool(
    tool: str, *args: str, input_text: str | None = None, timeout: int = 120
) -> str:
    return docker(
        "exec",
        "-i",
        KAFKA_CONTAINER,
        f"/opt/kafka/bin/{tool}",
        "--bootstrap-server",
        KAFKA_BOOTSTRAP,
        *args,
        input_text=input_text,
        timeout=timeout,
    )


def kafka_create_topic(topic: str) -> None:
    kafka_tool(
        "kafka-topics.sh",
        "--create",
        "--if-not-exists",
        "--topic",
        topic,
        "--partitions",
        "1",
        "--replication-factor",
        "1",
    )


def kafka_publish(topic: str, events: list[dict | str]) -> None:
    payload = "".join(
        (event if isinstance(event, str) else json.dumps(event)).rstrip("\n") + "\n"
        for event in events
    )
    kafka_tool(
        "kafka-console-producer.sh",
        "--topic",
        topic,
        "--producer-property",
        "acks=all",
        input_text=payload,
        timeout=180,
    )


def kafka_end_offset(topic: str) -> int:
    try:
        out = kafka_tool("kafka-get-offsets.sh", "--topic", topic)
        for line in out.splitlines():
            parts = line.split(":")
            if parts and parts[0] == topic and len(parts) >= 3:
                return int(parts[-1])
    except RuntimeError:
        pass
    return -1


def start_streaming(
    run_id: str,
    topic: str,
    max_offsets_per_trigger: int | None = None,
    trigger_seconds: int | None = None,
) -> str:
    image = docker(
        "inspect", STREAMING_CONTAINER, "--format", "{{.Config.Image}}"
    ).strip()
    name = f"e2e-streaming-{run_id}"
    spark_cmd = (
        "mkdir -p /tmp/spark-ivy/cache /tmp/spark-ivy/jars\n"
        "exec /opt/spark/bin/spark-submit "
        "--master local[2] "
        "--conf spark.jars.ivy=/tmp/spark-ivy "
        "--packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0,org.apache.hadoop:hadoop-aws:3.4.2,org.postgresql:postgresql:42.7.4 "
        "--conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 "
        "--conf spark.hadoop.fs.s3a.path.style.access=true "
        "--conf spark.hadoop.fs.s3a.connection.ssl.enabled=false "
        "--conf spark.hadoop.fs.s3a.aws.credentials.provider=org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider "
        "/opt/spark/jobs/orders_streaming.py"
    )
    max_offsets_env = (
        ["-e", f"KAFKA_MAX_OFFSETS_PER_TRIGGER={max_offsets_per_trigger}"]
        if max_offsets_per_trigger is not None
        else []
    )
    trigger_env = (
        ["-e", f"STREAMING_TRIGGER_SECONDS={trigger_seconds}"]
        if trigger_seconds is not None
        else []
    )
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "de_demo_net",
        "-e",
        "HOME=/tmp/spark-home",
        "-e",
        "PYSPARK_PYTHON=/usr/bin/python3",
        "-e",
        "KAFKA_BOOTSTRAP_SERVERS=kafka:9092",
        "-e",
        f"KAFKA_TOPIC={topic}",
        "-e",
        f"RAW_OUTPUT_PATH=s3a://de-practicum/e2e/{run_id}/orders_raw",
        "-e",
        f"RAW_CHECKPOINT_PATH=s3a://de-practicum/e2e/{run_id}/checkpoints/raw",
        "-e",
        f"POSTGRES_CHECKPOINT_PATH=s3a://de-practicum/e2e/{run_id}/checkpoints/pg",
        "-e",
        f"DEAD_LETTER_OUTPUT_PATH=s3a://de-practicum/e2e/{run_id}/orders_dead_letter",
        "-e",
        f"DEAD_LETTER_CHECKPOINT_PATH=s3a://de-practicum/e2e/{run_id}/checkpoints/dead_letter",
        "-e",
        f"RECONCILIATION_OUTPUT_PATH=s3a://de-practicum/e2e/{run_id}/orders_reconciliation",
        "-e",
        f"RECONCILIATION_CHECKPOINT_PATH=s3a://de-practicum/e2e/{run_id}/checkpoints/reconciliation",
        "-e",
        "KAFKA_FAIL_ON_DATA_LOSS=true",
        *max_offsets_env,
        *trigger_env,
        "-e",
        "POSTGRES_HOST=de-demo-postgres",
        "-e",
        "POSTGRES_PORT=5432",
        "-e",
        f"POSTGRES_DB={E2E_DB}",
        "-e",
        "POSTGRES_USER=app",
        "-e",
        "POSTGRES_PASSWORD=app",
        "-e",
        "AWS_ACCESS_KEY_ID=minio",
        "-e",
        "AWS_SECRET_ACCESS_KEY=minio123",
        "-e",
        "MINIO_BUCKET=de-practicum",
        "-v",
        f"{REPO_ROOT / 'spark' / 'jobs'}:/opt/spark/jobs:ro",
        # Shared with the always-on orders-streaming service, which warms the
        # cache at stack-up; without it every run re-resolves ~17 artifacts
        # (incl. the awssdk bundle) from Maven Central inside the landing budget.
        "-v",
        f"{IVY_CACHE_VOLUME}:/tmp/spark-ivy",
        image,
        "bash",
        "-lc",
        spark_cmd,
        timeout=90,
    )
    return name


def docker_rm(name: str) -> None:
    docker("rm", "-f", name)


def assert_container_running(name: str) -> None:
    """Fail fast when the ad-hoc streaming container dies.

    Called from the poll predicates *outside* `Probe`, whose whole job is to
    swallow exceptions; a crashed spark-submit must surface immediately rather
    than burn the full landing timeout.
    """
    try:
        state = docker(
            "inspect", name, "--format", "{{.State.Status}}|{{.State.ExitCode}}"
        ).strip()
    except RuntimeError as exc:
        raise RuntimeError(f"container {name} is gone: {exc}") from exc

    status, _, exit_code = state.partition("|")
    if status != "running":
        raise RuntimeError(
            f"container {name} stopped: status={status}, exit_code={exit_code}\n"
            f"{_docker_logs(name, tail=60)}"
        )


def _ensure_e2e_database() -> None:
    conn = psycopg2.connect(**{**PG, "dbname": "postgres"})
    try:
        conn.set_session(autocommit=True)
        with conn.cursor() as cur:
            cur.execute("select 1 from pg_database where datname = %s", (E2E_DB,))
            if cur.fetchone() is None:
                cur.execute(f'create database "{E2E_DB}"')
                print(f"[e2e] created postgres database '{E2E_DB}'", flush=True)
    finally:
        conn.close()
    with psycopg2.connect(**E2E_PG) as conn:
        with conn.cursor() as cur:
            # The writer/medallion metrics DDL creates its table but not the
            # schema, and they may start before the streaming job has run its
            # own initialise_database(). Guarantee both schemas up front.
            cur.execute("create schema if not exists stg")
            cur.execute("create schema if not exists marts")
            for table in (
                "marts.streaming_orders",
                "marts.streaming_country_totals",
                "marts.lakehouse_metrics",
                "stg.streaming_orders_batch",
            ):
                cur.execute("select to_regclass(%s) is not null", (table,))
                if cur.fetchone()[0]:
                    cur.execute(f"truncate table {table}")


def _trino_ready() -> bool:
    proc = subprocess.run(
        ["docker", "exec", TRINO_CONTAINER, "trino", "--execute", "SELECT 1"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode == 0


def _preflight() -> None:
    out = docker("ps", "--format", "{{.Names}}\t{{.Status}}")
    statuses: dict[str, str] = {}
    for line in out.splitlines():
        name, _, state = line.partition("\t")
        statuses[name] = state
    missing = [name for name in REQUIRED_CONTAINERS if name not in statuses]
    assert not missing, "required stack containers not running: " + ", ".join(missing)
    unhealthy = [
        f"{name} ({statuses[name]})"
        for name in REQUIRED_CONTAINERS
        if "unhealthy" in statuses[name].lower()
    ]
    assert not unhealthy, "unhealthy stack containers: " + ", ".join(unhealthy)

    with urllib.request.urlopen(f"{ICEBERG_CATALOG_URI}/v1/config", timeout=5) as resp:
        assert resp.status == 200, f"iceberg REST catalog not ready: HTTP {resp.status}"
    with psycopg2.connect(**PG) as conn:
        with conn.cursor() as cur:
            cur.execute("select 1")
    assert _trino_ready(), "trino coordinator not ready"
    _ensure_e2e_database()


def trino_raw(sql: str) -> str:
    return docker(
        "exec",
        TRINO_CONTAINER,
        "trino",
        "--catalog",
        "iceberg",
        "--execute",
        sql,
        "--output-format",
        "CSV_HEADER",
    )


def trino_scalar(sql: str) -> str:
    lines = [line for line in trino_raw(sql).splitlines() if line.strip()]
    assert len(lines) >= 2, f"expected header+row from trino: {sql}"
    return lines[1].strip().strip('"')


# --------------------------------------------------------------------------- #
# Iceberg / S3 helpers
# --------------------------------------------------------------------------- #
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


class Probe:
    """Wraps a poll function, keeping the last exception for diagnostics.

    The wrapped function is expected to raise on failure (e.g. catalog or S3
    unavailability); `__call__` returns ``None`` so the poll keeps retrying
    while ``last_error`` is retained and surfaced by ``wait_until`` on timeout.
    """

    def __init__(self, fn) -> None:
        self._fn = fn
        self.last_error: Exception | None = None

    def __call__(self):
        try:
            return self._fn()
        except Exception as exc:  # noqa: BLE001 - reported via wait_until
            self.last_error = exc
            return None


def table_rows(catalog: RestCatalog, identifier: str) -> int:
    return catalog.load_table(identifier).scan().to_arrow().num_rows


def landing_rows(fs: S3FileSystem, run_id: str) -> int:
    base = f"{BUCKET}/e2e/{run_id}/orders_raw"
    return arrow_dataset(base, filesystem=fs, format="parquet").count_rows()


def landing_source_metadata(fs: S3FileSystem, run_id: str):
    base = f"{BUCKET}/e2e/{run_id}/orders_raw"
    return arrow_dataset(base, filesystem=fs, format="parquet").to_table(
        columns=["kafka_partition", "kafka_offset"]
    )


def landing_business_versions(fs: S3FileSystem, run_id: str) -> list[int | None]:
    base = f"{BUCKET}/e2e/{run_id}/orders_raw"
    table = arrow_dataset(base, filesystem=fs, format="parquet").to_table(
        columns=["business_version"]
    )
    return table["business_version"].to_pylist()


def dead_letter_table(fs: S3FileSystem, run_id: str):
    base = f"{BUCKET}/e2e/{run_id}/orders_dead_letter"
    return arrow_dataset(base, filesystem=fs, format="parquet").to_table()


def reconciliation_table(fs: S3FileSystem, run_id: str):
    base = f"{BUCKET}/e2e/{run_id}/orders_reconciliation"
    return arrow_dataset(base, filesystem=fs, format="parquet").to_table()


def _pending_empty(state_file: Path) -> bool:
    try:
        return (
            json.loads(state_file.read_text(encoding="utf-8")).get("pending", None)
            == {}
        )
    except FileNotFoundError:
        return False


def _start_writer(run_id: str, state_file: Path, log_file: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "ICEBERG_CATALOG_URI": ICEBERG_CATALOG_URI,
            "ICEBERG_WAREHOUSE": ICEBERG_WAREHOUSE,
            "ICEBERG_NAMESPACE": f"e2e_{run_id}",
            "ICEBERG_TABLE": "orders",
            "MINIO_BUCKET": BUCKET,
            "LANDING_PREFIX": f"e2e/{run_id}/orders_raw",
            "S3_ENDPOINT": S3_ENDPOINT,
            "AWS_ACCESS_KEY_ID": ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
            "STATE_FILE": str(state_file),
            "BRONZE_OUTBOX_PREFIX": f"e2e/{run_id}/bronze_outbox",
            "POLL_INTERVAL_SECONDS": "1",
            "METRICS_ENABLED": "1",
            "POSTGRES_HOST": E2E_PG["host"],
            "POSTGRES_PORT": str(E2E_PG["port"]),
            "POSTGRES_DB": E2E_PG["dbname"],
            "POSTGRES_USER": E2E_PG["user"],
            "POSTGRES_PASSWORD": E2E_PG["password"],
        }
    )
    return _spawn(
        [sys.executable, "iceberg/writer/iceberg_writer.py"],
        env,
        log_file,
    )


def _start_medallion(run_id: str, log_file: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "ICEBERG_CATALOG_URI": ICEBERG_CATALOG_URI,
            "ICEBERG_WAREHOUSE": ICEBERG_WAREHOUSE,
            "BRONZE_NAMESPACE": f"e2e_{run_id}",
            "BRONZE_TABLE": "orders",
            "SILVER_NAMESPACE": f"e2e_{run_id}",
            "SILVER_TABLE": "orders_clean",
            "GOLD_NAMESPACE": f"e2e_{run_id}",
            "GOLD_TABLE": "orders_daily_metrics",
            "MEDALLION_INTERVAL_SECONDS": "2",
            "S3_ENDPOINT": S3_ENDPOINT,
            "AWS_ACCESS_KEY_ID": ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
            "METRICS_ENABLED": "1",
            "POSTGRES_HOST": E2E_PG["host"],
            "POSTGRES_PORT": str(E2E_PG["port"]),
            "POSTGRES_DB": E2E_PG["dbname"],
            "POSTGRES_USER": E2E_PG["user"],
            "POSTGRES_PASSWORD": E2E_PG["password"],
        }
    )
    return _spawn(
        [sys.executable, "iceberg/medallion/iceberg_medallion.py"],
        env,
        log_file,
    )


def _spawn(cmd: list[str], env: dict, log_file: Path) -> subprocess.Popen:
    fh = open(log_file, "ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=fh,
        stderr=subprocess.STDOUT,
    )
    proc._e2e_log_fh = fh
    return proc


def _terminate(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    fh = getattr(proc, "_e2e_log_fh", None)
    if fh is not None:
        fh.close()


def _docker_logs(container: str, tail: int = 25) -> str:
    proc = subprocess.run(
        ["docker", "logs", "--tail", str(tail), container],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return ""
    out = (proc.stdout + proc.stderr).strip()
    return f"--- {container} docker logs (tail) ---\n{out}" if out else ""


def _save_docker_logs(container: str, dest: Path) -> None:
    proc = subprocess.run(
        ["docker", "logs", container],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        dest.write_text(proc.stdout + proc.stderr, encoding="utf-8", errors="replace")


def _collect_logs(log_providers: tuple) -> str:
    parts: list[str] = []
    for provider in log_providers:
        if isinstance(provider, Path):
            try:
                tail = provider.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()[-25:]
            except OSError:
                continue
            if tail:
                parts.append(f"--- {provider.name} (tail) ---\n" + "\n".join(tail))
        elif callable(provider):
            text = provider()
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _capture_diagnostics(tmpdir: Path, ns: str) -> None:
    """Snapshot cluster state into the bundle before teardown wipes it.

    Runs in the `except` path, i.e. ahead of the `finally` cleanup that drops
    the namespace and the landing prefix, so the uploaded artifact stands on
    its own without needing the live stack.
    """

    def _write(name: str, producer) -> None:
        try:
            body = producer()
        except Exception as exc:  # noqa: BLE001 - diagnostics are best effort
            body = f"capture failed: {type(exc).__name__}: {exc}\n"
        try:
            (tmpdir / name).write_text(body, encoding="utf-8", errors="replace")
        except OSError:
            pass

    _write(
        "docker-ps.txt",
        lambda: docker("ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"),
    )
    _write("trino-schemas.txt", lambda: trino_raw("SHOW SCHEMAS"))
    _write("trino-tables.txt", lambda: trino_raw(f"SHOW TABLES FROM {ns}"))


def wait_until(
    predicate,
    timeout: int,
    desc: str,
    interval: int = 3,
    proc: subprocess.Popen | None = None,
    probes: tuple = (),
    logs: tuple = (),
):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        if proc is not None:
            rc = proc.poll()
            if rc is not None:
                raise AssertionError(
                    f"{desc}: helper process exited early (code {rc})\n"
                    f"{_collect_logs(logs)}"
                )
        last = predicate()
        if last:
            return last
        time.sleep(interval)

    detail = ""
    for probe in probes:
        err = probe.last_error
        if err is not None:
            detail += f"\nprobe error: {type(err).__name__}: {err}"
    detail += "\n" + _collect_logs(logs) if detail or _collect_logs(logs) else ""
    raise AssertionError(
        f"timed out after {timeout}s waiting for {desc} (last={last!r}){detail}"
    )


def _canonical_leak_counts(expected: dict, since) -> dict[str, int]:
    """Count E2E fixture traces in the canonical `dwh` database.

    A fresh stack may not have run the always-on streaming job's
    `initialise_database()` yet, so a missing canonical table is "no leak",
    not an error.
    """
    counts = {"streaming_orders": 0, "lakehouse_metrics": 0}
    with psycopg2.connect(**PG) as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('marts.streaming_orders') is not null")
            if cur.fetchone()[0]:
                cur.execute(
                    "select count(*) from marts.streaming_orders "
                    "where order_id like 'clean-%' or order_id like 'dup-%'"
                )
                counts["streaming_orders"] = cur.fetchone()[0]
            cur.execute("select to_regclass('marts.lakehouse_metrics') is not null")
            if cur.fetchone()[0]:
                cur.execute(
                    "select count(*) from marts.lakehouse_metrics "
                    "where bronze_rows=%s and silver_rows=%s "
                    "and duplicates_removed=%s and quality_violations=%s "
                    "and metric_ts >= %s",
                    (
                        expected["bronze_rows"],
                        expected["silver_rows"],
                        expected["duplicates_removed"],
                        expected["total_violations"],
                        since,
                    ),
                )
                counts["lakehouse_metrics"] = cur.fetchone()[0]
    return counts


def _pg_now() -> object:
    """Watermark read from Postgres, so polls never depend on runner clock skew."""
    with psycopg2.connect(**E2E_PG) as conn:
        with conn.cursor() as cur:
            cur.execute("select now()")
            return cur.fetchone()[0]


def _e2e_sink_rows(expected_rows: int) -> bool:
    with psycopg2.connect(**E2E_PG) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from marts.streaming_orders")
            return cur.fetchone()[0] == expected_rows


def _metrics_match(expected: dict, load_ids: list[str], since) -> bool:
    with psycopg2.connect(**E2E_PG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select load_id, rows_processed, status from marts.lakehouse_metrics "
                "where source='writer' and load_id = ANY(%s)",
                (load_ids,),
            )
            writer_rows = cur.fetchall()
            # `since` scopes this to the current run: medallion metrics carry no
            # load_id, so a count-tuple match alone would be satisfied by rows
            # left behind by an earlier run.
            cur.execute(
                "select status from marts.lakehouse_metrics where source='medallion' "
                "and metric_ts >= %s "
                "and bronze_rows=%s and silver_rows=%s and duplicates_removed=%s "
                "and quality_violations=%s order by metric_ts desc limit 20",
                (
                    since,
                    expected["bronze_rows"],
                    expected["silver_rows"],
                    expected["duplicates_removed"],
                    expected["total_violations"],
                ),
            )
            medallion_statuses = [r[0] for r in cur.fetchall()]

    writer_load_ids = {row[0] for row in writer_rows}
    if writer_load_ids != set(load_ids):
        return False
    if not all(status == "success" for _, _, status in writer_rows):
        return False
    if sum(rows for _, rows, _ in writer_rows) != expected["bronze_rows"]:
        return False
    return any(status == "success" for status in medallion_statuses)


# --------------------------------------------------------------------------- #
# The test
# --------------------------------------------------------------------------- #
@pytest.mark.e2e
def test_deterministic_nightly_pipeline() -> None:
    fixture = build_fixture()
    expected = expected_pipeline(fixture)

    assert all("business_version" in event for event in fixture)
    assert expected["total_events"] == 101
    assert expected["landing_rows"] == 99
    assert expected["silver_rows"] == 95
    assert expected["duplicates_removed"] == 4
    assert expected["total_violations"] == 7
    assert expected["uk_delivered_total"] == 90.0
    assert expected["cancelled_count"] == 2

    _preflight()

    run_id = uuid.uuid4().hex[:8]
    topic = f"orders_e2e_{run_id}"
    ns = f"e2e_{run_id}"
    tmpdir = Path(tempfile.mkdtemp(prefix="e2e-"))
    state_file = tmpdir / "ingested.json"
    writer_log = tmpdir / "iceberg_writer.log"
    medallion_log = tmpdir / "iceberg_medallion.log"

    stream_name: str | None = None
    proc_writer: subprocess.Popen | None = None
    proc_medallion: subprocess.Popen | None = None
    success = False
    run_started_at = _pg_now()

    try:
        print(f"[e2e] run_id={run_id} topic={topic} namespace={ns}", flush=True)

        kafka_create_topic(topic)
        kafka_publish(topic, fixture)
        offset = wait_until(
            lambda: kafka_end_offset(topic) == expected["total_events"],
            60,
            "kafka durability",
        )
        assert offset

        stream_name = start_streaming(run_id, topic)
        landing_probe = Probe(lambda: landing_rows(_fs(), run_id))

        def landing_reached() -> bool:
            assert_container_running(stream_name)
            return landing_probe() == expected["landing_rows"]

        wait_until(
            landing_reached,
            300,
            "landing parquet",
            probes=(landing_probe,),
            logs=(lambda: _docker_logs(stream_name),),
        )
        landed_versions = landing_business_versions(_fs(), run_id)
        assert landed_versions and all(version is not None for version in landed_versions)
        assert Counter(landed_versions) == Counter(
            event["business_version"]
            for event in fixture
            if event["order_id"] is not None
        )
        sink_probe = Probe(lambda: _e2e_sink_rows(expected["silver_rows"]))

        def sink_reached() -> bool:
            assert_container_running(stream_name)
            return bool(sink_probe())

        wait_until(
            sink_reached,
            60,
            f"postgres sink isolation (database '{E2E_DB}')",
            probes=(sink_probe,),
            logs=(lambda: _docker_logs(stream_name),),
        )
        # Capture the streaming log before removal, so a later failure still has it.
        _save_docker_logs(stream_name, tmpdir / "e2e_streaming_docker.log")
        docker_rm(stream_name)
        stream_name = None

        leaked = _canonical_leak_counts(expected, run_started_at)
        assert leaked == {
            "streaming_orders": 0,
            "lakehouse_metrics": 0,
        }, f"e2e traces leaked into canonical {PG['dbname']}: {leaked}"

        proc_writer = _start_writer(run_id, state_file, writer_log)
        bronze_probe = Probe(lambda: table_rows(_catalog(), f"{ns}.orders"))
        wait_until(
            lambda: bronze_probe() == expected["bronze_rows"]
            and _pending_empty(state_file),
            180,
            "bronze ingest",
            proc=proc_writer,
            probes=(bronze_probe,),
            logs=(writer_log,),
        )
        bronze = _catalog().load_table(f"{ns}.orders")
        snapshots = list(bronze.metadata.snapshots)
        assert snapshots, "no snapshots on bronze"
        load_ids = [s.summary.additional_properties["load-id"] for s in snapshots]
        assert len(load_ids) == len(set(load_ids)), "duplicate load-ids on bronze"
        _terminate(proc_writer)
        proc_writer = None

        medallion_started_at = _pg_now()
        proc_medallion = _start_medallion(run_id, medallion_log)
        silver_probe = Probe(lambda: table_rows(_catalog(), f"{ns}.orders_clean"))
        gold_probe = Probe(lambda: table_rows(_catalog(), f"{ns}.orders_daily_metrics"))
        wait_until(
            lambda: silver_probe() == expected["silver_rows"]
            and gold_probe() == expected["gold_row_count"],
            180,
            "silver/gold build",
            proc=proc_medallion,
            probes=(silver_probe, gold_probe),
            logs=(medallion_log,),
        )
        time.sleep(4)
        assert table_rows(_catalog(), f"{ns}.orders_clean") == expected["silver_rows"]
        assert (
            table_rows(_catalog(), f"{ns}.orders_daily_metrics")
            == expected["gold_row_count"]
        )
        _terminate(proc_medallion)
        proc_medallion = None

        assert (
            int(trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.orders"))
            == expected["bronze_rows"]
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT count(*) FROM iceberg.{ns}.orders "
                    "WHERE business_version IS NULL"
                )
            )
            == 0
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT max(business_version) FROM iceberg.{ns}.orders "
                    "WHERE order_id = 'dup-1'"
                )
            )
            == 5
        )
        for version, count in expected["business_version_counts"].items():
            assert (
                int(
                    trino_scalar(
                        f"SELECT count(*) FROM iceberg.{ns}.orders "
                        f"WHERE business_version = {version}"
                    )
                )
                == count
            )
        assert (
            int(
                trino_scalar(
                    f"SELECT count(DISTINCT order_id) FROM iceberg.{ns}.orders"
                )
            )
            == expected["silver_rows"]
        )
        assert (
            int(trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.orders_clean"))
            == expected["silver_rows"]
        )
        assert (
            float(
                trino_scalar(
                    f"SELECT amount FROM iceberg.{ns}.orders_clean WHERE order_id = 'dup-1'"
                )
            )
            == 30.0
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT business_version FROM iceberg.{ns}.orders_clean "
                    "WHERE order_id = 'dup-1'"
                )
            )
            == 5
        )
        assert (
            trino_scalar(
                f"SELECT status FROM iceberg.{ns}.orders_clean WHERE order_id = 'dup-1'"
            )
            == "delivered"
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT sum(orders_count) FROM iceberg.{ns}.orders_daily_metrics"
                )
            )
            == expected["silver_rows"]
        )
        assert (
            abs(
                float(
                    trino_scalar(
                        f"SELECT sum(total_amount) FROM iceberg.{ns}.orders_daily_metrics"
                    )
                )
                - expected["total_revenue"]
            )
            < 1e-6
        )
        assert (
            abs(
                float(
                    trino_scalar(
                        f"SELECT total_amount FROM iceberg.{ns}.orders_daily_metrics "
                        "WHERE country = 'UK' AND status = 'paid'"
                    )
                )
                - expected["uk_paid_total"]
            )
            < 1e-6
        )
        assert (
            abs(
                float(
                    trino_scalar(
                        f"SELECT total_amount FROM iceberg.{ns}.orders_daily_metrics "
                        "WHERE country = 'UK' AND status = 'delivered'"
                    )
                )
                - 90.0
            )
            < 1e-6
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT orders_count FROM iceberg.{ns}.orders_daily_metrics "
                    "WHERE country = 'US' AND status = 'cancelled'"
                )
            )
            == 2
        )
        assert (
            abs(
                float(
                    trino_scalar(
                        f"SELECT total_amount FROM iceberg.{ns}.orders_daily_metrics "
                        "WHERE country = 'ES' AND status = 'paid'"
                    )
                )
                - expected["gold_groups"][(FIXTURE_DATE, "ES", "paid")]["total"]
            )
            < 1e-6
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT count(*) FROM iceberg.{ns}.orders_clean WHERE country IS NULL"
                )
            )
            == 1
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT count(*) FROM iceberg.{ns}.orders_clean WHERE amount IS NULL"
                )
            )
            == 1
        )
        assert (
            int(
                trino_scalar(
                    f"SELECT orders_count FROM iceberg.{ns}.orders_daily_metrics WHERE event_date IS NULL"
                )
            )
            == 1
        )

        metrics_probe = Probe(
            lambda: _metrics_match(expected, load_ids, medallion_started_at)
        )
        wait_until(
            lambda: metrics_probe(),
            60,
            "pipeline metrics",
            probes=(metrics_probe,),
        )
        success = True
    except Exception:
        try:
            (tmpdir / "failure.txt").write_text(
                traceback.format_exc(), encoding="utf-8", errors="replace"
            )
        except OSError:
            pass
        _capture_diagnostics(tmpdir, ns)
        raise
    finally:
        _terminate(proc_writer)
        _terminate(proc_medallion)
        if stream_name:
            try:
                _save_docker_logs(stream_name, tmpdir / "e2e_streaming_docker.log")
            except OSError:
                pass
            try:
                docker_rm(stream_name)
            except RuntimeError:
                pass
        catalog = _catalog()
        for ident in (
            f"{ns}.orders",
            f"{ns}.orders_clean",
            f"{ns}.orders_daily_metrics",
        ):
            try:
                catalog.drop_table(ident)
            except Exception:
                pass
        try:
            catalog.drop_namespace(ns)
        except Exception:
            pass
        try:
            _fs().delete_dir(f"{BUCKET}/e2e/{run_id}")
        except Exception:
            pass
        try:
            kafka_tool("kafka-topics.sh", "--delete", "--topic", topic)
        except RuntimeError:
            pass
        if success:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            artifact_dir = REPO_ROOT / "artifacts" / "e2e-logs" / run_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copytree(tmpdir, artifact_dir, dirs_exist_ok=True)
            except OSError as exc:
                print(
                    f"[e2e] could not preserve logs in {artifact_dir}: {exc}",
                    flush=True,
                )
            print(f"[e2e] run failed; logs preserved at {artifact_dir}", flush=True)
