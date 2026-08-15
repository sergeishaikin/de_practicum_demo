from __future__ import annotations

import os
import traceback
from datetime import datetime, timedelta

import psycopg2
import trino

from airflow.sdk import dag, get_current_context, task
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
MAINTENANCE_TARGETS = [
    {"schema": schema, "table": table} for schema, table in MAINTENANCE_TABLES
]

MAINTENANCE_DAG_DOC = """
## Lakehouse maintenance

Runs Iceberg maintenance independently for each managed table. Every mapped
task instance performs `optimize`, snapshot expiry, orphan-file cleanup, and
then captures its post-maintenance snapshot count. Each mapped task commits its
own success or failure result to `marts.maintenance_runs` before returning or
re-raising the maintenance error.

The retention contract is validated while the DAG is imported so an unsafe
configuration cannot reach snapshot expiry.
"""

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


def _fresh_snapshot_count(schema: str, table: str) -> int | None:
    """Read the current snapshot count without reusing a failed Trino session."""
    conn = None
    try:
        conn = _trino_connect()
        return _snapshot_count(conn, schema, table)
    except Exception:
        print(f"best-effort snapshot count failed for {schema}.{table}", flush=True)
        traceback.print_exc()
        return None
    finally:
        if conn is not None:
            conn.close()


def _upsert_audit(
    airflow_run_id: str,
    table_name: str,
    before_snapshots: int | None,
    after_snapshots: int | None,
    status: str,
) -> None:
    with psycopg2.connect(**DWH_CONN) as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(AUDIT_DDL)
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
                    table_name,
                    before_snapshots,
                    after_snapshots,
                    status,
                ),
            )
        pg_conn.commit()


def _log_maintenance_exception(exc: Exception, operation: str, table_name: str) -> None:
    error = getattr(exc, "error", None)
    query_id = getattr(exc, "query_id", None)
    if query_id is None and isinstance(error, dict):
        query_id = error.get("queryId")
    print(
        f"maintenance failed: table={table_name} operation={operation} "
        f"trino_query_id={query_id or 'unavailable'} exception={exc!r}",
        flush=True,
    )
    traceback.print_exc()


@dag(
    dag_id="lakehouse_maintenance",
    dag_display_name="Lakehouse Table Maintenance",
    description="Maintain each managed Iceberg table and audit snapshot counts.",
    doc_md=MAINTENANCE_DAG_DOC,
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
    @task(map_index_template="{{ table_name }}", max_active_tis_per_dagrun=1)
    def maintain_table(target: dict[str, str], airflow_run_id: str) -> dict:
        schema = target["schema"]
        table = target["table"]
        full_name = f"{schema}.{table}"
        get_current_context()["table_name"] = full_name
        before_count = None
        after_count = None
        operation = "capture_before"

        conn = None
        try:
            conn = _trino_connect()
            before_count = _snapshot_count(conn, schema, table)
            statements = (
                (
                    "optimize",
                    f"alter table iceberg.{schema}.{table} "
                    f"execute optimize(file_size_threshold => '{FILE_SIZE_THRESHOLD}')",
                ),
                (
                    "expire_snapshots",
                    f"alter table iceberg.{schema}.{table} "
                    f"execute expire_snapshots("
                    f"retention_threshold => '{RETENTION}', "
                    f"retain_last => {RETAIN_LAST}, "
                    f"clean_expired_metadata => false)",
                ),
                (
                    "remove_orphan_files",
                    f"alter table iceberg.{schema}.{table} "
                    f"execute remove_orphan_files(retention_threshold => '{RETENTION}')",
                ),
            )
            for operation, statement in statements:
                cursor = conn.cursor()
                try:
                    cursor.execute(statement)
                    conn.commit()
                finally:
                    cursor.close()
                print(f"{operation}: {full_name} done", flush=True)

            operation = "capture_after"
            after_count = _snapshot_count(conn, schema, table)
        except Exception as exc:
            _log_maintenance_exception(exc, operation, full_name)
            after_count = _fresh_snapshot_count(schema, table)
            try:
                _upsert_audit(
                    airflow_run_id,
                    full_name,
                    before_count,
                    after_count,
                    f"failed:{operation}",
                )
            except Exception as audit_exc:
                print(
                    f"failure audit could not be committed for {full_name}: "
                    f"{audit_exc!r}",
                    flush=True,
                )
                traceback.print_exc()
                raise exc from audit_exc
            raise
        finally:
            if conn is not None:
                conn.close()

        reduced = before_count is not None and after_count < before_count
        status = "ok" if after_count <= RETAIN_LAST + 2 or reduced else "noop"
        result = {
            "table_name": full_name,
            "before_snapshots": before_count,
            "after_snapshots": after_count,
            "status": status,
        }
        _upsert_audit(
            airflow_run_id,
            full_name,
            before_count,
            after_count,
            status,
        )
        print(
            f"maintenance {full_name}: before={before_count} "
            f"after={after_count} ({status})",
            flush=True,
        )
        return result

    maintain_table.partial(airflow_run_id="{{ run_id }}").expand(
        target=MAINTENANCE_TARGETS
    )


lakehouse_maintenance()
