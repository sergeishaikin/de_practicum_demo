from __future__ import annotations

import os
from datetime import datetime, timedelta

import psycopg2
import trino

from airflow.decorators import dag, task
from recovery_contract import validate_retention_contract

TRINO_HOST = os.getenv("TRINO_HOST", "trino")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
TRINO_USER = os.getenv("TRINO_USER", "admin")

DWH_CONN = {
    "host": os.getenv("DWH_HOST", "de-demo-postgres"),
    "port": int(os.getenv("DWH_PORT", "5432")),
    "dbname": os.getenv("DWH_DB", "dwh"),
    "user": os.getenv("DWH_USER", "app"),
    "password": os.getenv("DWH_PASSWORD", "app"),
}

MAINTENANCE_TABLES = [
    ("bronze", "orders"),
    ("silver", "orders_clean"),
    ("gold", "orders_daily_metrics"),
]

RETENTION = os.getenv("MAINTENANCE_RETENTION", "2h")
RECOVERY_HORIZON = os.getenv("MAINTENANCE_RECOVERY_HORIZON", "1h")
RECOVERY_SAFETY_MARGIN = os.getenv("MAINTENANCE_RECOVERY_SAFETY_MARGIN", "15m")
RETAIN_LAST = int(os.getenv("MAINTENANCE_RETAIN_LAST", "5"))
FILE_SIZE_THRESHOLD = os.getenv("MAINTENANCE_FILE_SIZE_THRESHOLD", "10MB")

# Fail at DAG import time so an unsafe deployment cannot reach snapshot expiry.
RETENTION_CONTRACT = validate_retention_contract(
    RETENTION,
    RECOVERY_HORIZON,
    RECOVERY_SAFETY_MARGIN,
)

AUDIT_DDL = """
create table if not exists marts.maintenance_runs (
    run_id text not null,
    run_ts timestamptz not null default now(),
    table_name text not null,
    before_snapshots bigint,
    after_snapshots bigint,
    status text not null,
    primary key (run_id, table_name)
);
"""


def _trino_connect():
    return trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog="iceberg",
        schema="bronze",
    )


def _snapshot_count(conn, schema: str, table: str) -> int:
    cur = conn.cursor()
    try:
        cur.execute(f'select count(*) from iceberg."{schema}"."{table}$snapshots"')
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        cur.close()


@dag(
    dag_id="lakehouse_maintenance",
    start_date=datetime(2024, 1, 1),
    schedule="0 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        "execution_timeout": timedelta(minutes=15),
        "retries": 0,
    },
    tags=["demo", "iceberg", "maintenance"],
)
def lakehouse_maintenance():
    @task
    def capture_before() -> dict:
        conn = _trino_connect()
        try:
            return {
                f"{schema}.{table}": _snapshot_count(conn, schema, table)
                for schema, table in MAINTENANCE_TABLES
            }
        finally:
            conn.close()

    @task
    def optimize_tables() -> None:
        conn = _trino_connect()
        try:
            for schema, table in MAINTENANCE_TABLES:
                stmt = (
                    f"alter table iceberg.{schema}.{table} "
                    f"execute optimize(file_size_threshold => '{FILE_SIZE_THRESHOLD}')"
                )
                conn.cursor().execute(stmt)
                conn.commit()
                print(f"optimize: {schema}.{table} done", flush=True)
        finally:
            conn.close()

    @task
    def expire_snapshots_tables() -> None:
        conn = _trino_connect()
        try:
            for schema, table in MAINTENANCE_TABLES:
                stmt = (
                    f"alter table iceberg.{schema}.{table} "
                    f"execute expire_snapshots("
                    f"retention_threshold => '{RETENTION}', "
                    f"retain_last => {RETAIN_LAST}, "
                    f"clean_expired_metadata => true)"
                )
                conn.cursor().execute(stmt)
                conn.commit()
                print(f"expire_snapshots: {schema}.{table} done", flush=True)
        finally:
            conn.close()

    @task
    def remove_orphan_files_tables() -> None:
        conn = _trino_connect()
        try:
            for schema, table in MAINTENANCE_TABLES:
                stmt = (
                    f"alter table iceberg.{schema}.{table} "
                    f"execute remove_orphan_files(retention_threshold => '{RETENTION}')"
                )
                conn.cursor().execute(stmt)
                conn.commit()
                print(f"remove_orphan_files: {schema}.{table} done", flush=True)
        finally:
            conn.close()

    @task
    def write_audit(before: dict, airflow_run_id: str) -> None:
        conn = _trino_connect()
        try:
            after = {
                f"{schema}.{table}": _snapshot_count(conn, schema, table)
                for schema, table in MAINTENANCE_TABLES
            }
        finally:
            conn.close()

        rows = []
        for full_name, after_count in after.items():
            before_count = before.get(full_name)
            reduced = before_count is not None and after_count < before_count
            status = "ok" if after_count <= RETAIN_LAST + 2 or reduced else "noop"
            rows.append((full_name, before_count, after_count, status))

        for full_name, before_count, after_count, status in rows:
            print(
                f"maintenance {full_name}: before={before_count} "
                f"after={after_count} ({status})",
                flush=True,
            )

        with psycopg2.connect(**DWH_CONN) as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(AUDIT_DDL)
                for full_name, before_count, after_count, status in rows:
                    cur.execute(
                        """
                        insert into marts.maintenance_runs (
                            run_id, run_ts, table_name,
                            before_snapshots, after_snapshots, status
                        ) values (%s, now(), %s, %s, %s, %s)
                        on conflict (run_id, table_name) do update set
                            run_ts = excluded.run_ts,
                            before_snapshots = excluded.before_snapshots,
                            after_snapshots = excluded.after_snapshots,
                            status = excluded.status
                        """,
                        (
                            airflow_run_id,
                            full_name,
                            before_count,
                            after_count,
                            status,
                        ),
                    )
            pg_conn.commit()

    before = capture_before()
    optimize = optimize_tables()
    expire = expire_snapshots_tables()
    orphan = remove_orphan_files_tables()
    audit = write_audit(before=before, airflow_run_id="{{ run_id }}")

    before >> optimize >> expire >> orphan >> audit


lakehouse_maintenance()
