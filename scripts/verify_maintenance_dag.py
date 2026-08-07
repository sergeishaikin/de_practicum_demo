"""Nightly end-to-end check of the lakehouse_maintenance DAG.

Triggers the DAG in the airflow container and verifies audit rows land in
Postgres `marts.maintenance_runs` for every configured table. Exits non-zero on
failure so CI can gate on it.

Assumes the full stack is up: airflow at `de-demo-airflow` (docker exec) and
Postgres published on the host at `localhost:15432` (override via env).
"""

from __future__ import annotations

import os
import subprocess
import time

import psycopg2

PG = {
    "host": os.getenv("DWH_HOST", "localhost"),
    "port": int(os.getenv("DWH_PORT", "15432")),
    "dbname": os.getenv("DWH_DB", "dwh"),
    "user": os.getenv("DWH_USER", "app"),
    "password": os.getenv("DWH_PASSWORD", "app"),
}

DAG_ID = "lakehouse_maintenance"
CONTAINER = "de-demo-airflow"
EXPECTED_TABLES = {
    "bronze.orders",
    "silver.orders_clean",
    "gold.orders_daily_metrics",
}
LOOKBACK_MINUTES = 20
POLL_SECONDS = 10
TIMEOUT_SECONDS = int(os.getenv("VERIFY_TIMEOUT_SECONDS", "300"))


def trigger() -> None:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "airflow",
            "dags",
            "trigger",
            DAG_ID,
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"failed to trigger {DAG_ID}: {proc.stderr.strip()}")


def recent_audit_rows() -> list[tuple[str, str]]:
    with psycopg2.connect(**PG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select table_name, status
                from marts.maintenance_runs
                where run_ts > now() - interval '%s minutes'
                """,
                (LOOKBACK_MINUTES,),
            )
            return list(cur.fetchall())


def main() -> int:
    trigger()
    print(f"triggered {DAG_ID}; waiting up to {TIMEOUT_SECONDS}s for audit rows")

    deadline = time.time() + TIMEOUT_SECONDS
    rows: list[tuple[str, str]] = []
    while time.time() < deadline:
        try:
            rows = recent_audit_rows()
        except psycopg2.Error as exc:
            print(f"db not ready yet: {exc.pgcode} {exc.pgerror.strip()[:120]}")
        got = {row[0] for row in rows}
        if EXPECTED_TABLES.issubset(got):
            break
        time.sleep(POLL_SECONDS)

    got = {row[0] for row in rows}
    missing = sorted(EXPECTED_TABLES - got)
    if missing:
        print(f"FAIL: no fresh audit rows for {missing}")
        print(f"  rows found: {rows}")
        return 1

    print(f"OK: audit rows landed for all tables (lookback {LOOKBACK_MINUTES}m):")
    for table, status in sorted(rows):
        print(f"  {table}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
