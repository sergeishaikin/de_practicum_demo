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
import uuid
from collections import Counter
from datetime import datetime, timezone

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


def make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"maintenance_verify_{timestamp}_{uuid.uuid4().hex[:12]}"


def trigger(run_id: str) -> None:
    proc = _airflow("dags", "trigger", "-r", run_id, DAG_ID)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"failed to trigger {DAG_ID} run_id={run_id}: {detail}")


def audit_rows_for_run(run_id: str) -> list[tuple[str, str, str]]:
    with psycopg2.connect(**PG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select run_id, table_name, status
                from marts.maintenance_runs
                where run_id = %s
                """,
                (run_id,),
            )
            return list(cur.fetchall())


def classify_audit_rows(
    run_id: str, rows: list[tuple[str, str, str]]
) -> tuple[bool, str]:
    if len(rows) != len(EXPECTED_TABLES):
        return False, f"expected 3 rows, found {len(rows)}"

    row_run_ids = {row[0] for row in rows}
    if row_run_ids != {run_id}:
        return False, f"unexpected run IDs: {sorted(row_run_ids)}"

    target_counts = Counter(row[1] for row in rows)
    duplicates = sorted(table for table, count in target_counts.items() if count != 1)
    missing = sorted(EXPECTED_TABLES - target_counts.keys())
    extra = sorted(target_counts.keys() - EXPECTED_TABLES)
    if duplicates or missing or extra:
        return (
            False,
            f"target mismatch: duplicates={duplicates} missing={missing} extra={extra}",
        )

    failed = sorted(
        (table, status) for _, table, status in rows if status not in {"ok", "noop"}
    )
    if failed:
        return False, f"non-success statuses: {failed}"
    return True, "exact audit rows are successful"


def dag_run_state(run_id: str) -> str:
    proc = _airflow("dags", "state", DAG_ID, run_id)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(
            f"could not read DagRun state for {run_id}: {detail or 'empty output'}"
        )
    lines = [line.strip().lower() for line in proc.stdout.splitlines() if line.strip()]
    if not lines or lines[-1] not in {"queued", "running", "success", "failed"}:
        raise RuntimeError(
            f"malformed DagRun state output for {run_id}: {proc.stdout!r}"
        )
    return lines[-1]


def main() -> int:
    ensure_dag_ready()
    run_id = make_run_id()
    print(f"maintenance verification run_id={run_id}", flush=True)
    trigger(run_id)
    print(
        f"triggered {DAG_ID} once; waiting up to {TIMEOUT_SECONDS}s for "
        "the exact DagRun and audit key",
        flush=True,
    )

    deadline = time.time() + TIMEOUT_SECONDS
    rows: list[tuple[str, str, str]] = []
    state = "queued"
    audit_reason = "no rows yet"
    while time.time() < deadline:
        state = dag_run_state(run_id)
        rows = audit_rows_for_run(run_id)
        audit_ok, audit_reason = classify_audit_rows(run_id, rows)
        if state == "failed":
            print(f"FAIL: exact DagRun {run_id} failed; rows={rows}")
            return 1
        if state == "success":
            if audit_ok:
                break
            print(
                f"FAIL: exact DagRun {run_id} succeeded without an exact "
                f"successful audit set: {audit_reason}; rows={rows}"
            )
            return 1
        time.sleep(POLL_SECONDS)
    else:
        print(
            f"FAIL: timed out waiting for exact run {run_id}: "
            f"state={state} audit={audit_reason} rows={rows}"
        )
        return 1

    print(f"OK: exact DagRun {run_id} succeeded with one audit row per target:")
    for _, table, status in sorted(rows):
        print(f"  {table}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
