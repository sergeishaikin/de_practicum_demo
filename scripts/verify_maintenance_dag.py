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
DAG_READY_TIMEOUT_SECONDS = int(os.getenv("DAG_READY_TIMEOUT_SECONDS", "300"))


def _airflow(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", CONTAINER, "airflow", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ensure_dag_ready() -> None:
    """Wait for the DAG to be parsed, then unpause it.

    The stack sets AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True, so on a
    fresh deployment (any CI runner) the DAG exists but is paused. `dags
    trigger` still succeeds and creates a run, but the scheduler never
    executes it — the verification then times out against an empty
    marts.maintenance_runs. A long-lived local stack hides this, because the
    DAG was unpaused once and that state persists in the metadata volume.
    """
    deadline = time.time() + DAG_READY_TIMEOUT_SECONDS
    last = ""
    while time.time() < deadline:
        proc = _airflow("dags", "list", "--output", "plain")
        if proc.returncode == 0 and DAG_ID in proc.stdout:
            break
        last = (proc.stderr or proc.stdout).strip()[:200]
        print(f"waiting for {DAG_ID} to be parsed by the scheduler...")
        time.sleep(POLL_SECONDS)
    else:
        raise RuntimeError(f"{DAG_ID} never appeared in the DagBag: {last}")

    proc = _airflow("dags", "unpause", DAG_ID)
    if proc.returncode != 0:
        raise RuntimeError(f"failed to unpause {DAG_ID}: {proc.stderr.strip()}")
    print(f"{DAG_ID} is parsed and unpaused")


def trigger() -> None:
    proc = _airflow("dags", "trigger", DAG_ID)
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
    ensure_dag_ready()
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
