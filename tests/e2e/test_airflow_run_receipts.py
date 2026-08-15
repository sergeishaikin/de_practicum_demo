"""Read-only verification of the completed Quick 260815-ulp Airflow receipts.

Opt in with ``AIRFLOW_RECEIPT_E2E=1``. Run IDs default to the immutable receipt
recorded on 2026-08-15 and may be overridden with ``MAINTENANCE_RECEIPT_RUN_ID``
and ``BATCH_RECEIPT_RUN_ID``. This test never triggers or changes a DagRun.
"""

from __future__ import annotations

import os
import subprocess

import pytest

MAINTENANCE_RUN_ID = os.getenv(
    "MAINTENANCE_RECEIPT_RUN_ID",
    "maintenance_verify_20260815T222907391492Z_3be4ca723766",
)
BATCH_RUN_ID = os.getenv(
    "BATCH_RECEIPT_RUN_ID", "batch_verify_20260815T223250865259Z_6c9d0f4252d6"
)

pytestmark = [pytest.mark.e2e, pytest.mark.airflow]


def _docker(*args: str) -> str:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout.strip()


def _psql(database: str, user: str, sql: str) -> list[list[str]]:
    output = _docker(
        "exec",
        "de-demo-postgres",
        "psql",
        "-XAt",
        "-F",
        "|",
        "-U",
        user,
        "-d",
        database,
        "-c",
        sql,
    )
    return [line.split("|") for line in output.splitlines() if line.strip()]


def _quote(value: str) -> str:
    return value.replace("'", "''")


@pytest.fixture(scope="module", autouse=True)
def require_explicit_receipt_gate() -> None:
    if os.getenv("AIRFLOW_RECEIPT_E2E") != "1":
        pytest.skip("set AIRFLOW_RECEIPT_E2E=1 for read-only receipt verification")
    names = set(_docker("ps", "--format", "{{.Names}}").splitlines())
    required = {"de-demo-postgres", "de-demo-iceberg-medallion"}
    if not required <= names:
        pytest.skip(f"receipt services absent: {sorted(required - names)}")


def test_exact_airflow_dagruns_and_single_attempt_task_instances() -> None:
    maintenance = _quote(MAINTENANCE_RUN_ID)
    batch = _quote(BATCH_RUN_ID)
    runs = _psql(
        "airflow_meta",
        "airflow",
        "select dag_id, run_id, state from dag_run "
        f"where (dag_id='lakehouse_maintenance' and run_id='{maintenance}') "
        f"or (dag_id='demo_core_marts_pipeline' and run_id='{batch}') "
        "order by dag_id;",
    )
    assert runs == [
        ["demo_core_marts_pipeline", BATCH_RUN_ID, "success"],
        ["lakehouse_maintenance", MAINTENANCE_RUN_ID, "success"],
    ]

    maintenance_tasks = _psql(
        "airflow_meta",
        "airflow",
        "select task_id, map_index, state, try_number, max_tries from task_instance "
        f"where dag_id='lakehouse_maintenance' and run_id='{maintenance}' "
        "order by map_index;",
    )
    assert maintenance_tasks == [
        ["maintain_table", "0", "success", "1", "0"],
        ["maintain_table", "1", "success", "1", "0"],
        ["maintain_table", "2", "success", "1", "0"],
    ]

    batch_tasks = _psql(
        "airflow_meta",
        "airflow",
        "select task_id, state, try_number, max_tries from task_instance "
        f"where dag_id='demo_core_marts_pipeline' and run_id='{batch}' "
        "order by task_id;",
    )
    assert batch_tasks == [
        [task, "success", "1", "0"]
        for task in sorted(
            [
                "load_raw_csv_to_stg",
                "validate_staging",
                "rebuild_core_and_marts",
                "check_payment_reconcile",
                "write_audit",
            ]
        )
    ]


def test_exact_dwh_audits_and_persisted_runtime_mode() -> None:
    maintenance = _quote(MAINTENANCE_RUN_ID)
    batch = _quote(BATCH_RUN_ID)
    audit = _psql(
        "dwh",
        "app",
        "select table_name, before_snapshots, after_snapshots, status "
        f"from marts.maintenance_runs where run_id='{maintenance}' order by table_name;",
    )
    assert audit == [
        ["bronze.orders", "5", "5", "ok"],
        ["gold.orders_daily_metrics", "205", "170", "ok"],
        ["silver.orders_clean", "202", "165", "ok"],
    ]

    pipeline = _psql(
        "dwh",
        "app",
        "select status, stg_orders, stg_order_items, core_order_items, "
        "mart_sales_days, duplicate_grain_rows, null_key_rows, max_reconcile_diff "
        f"from marts.pipeline_runs where run_id='{batch}';",
    )
    assert pipeline == [["success", "1000", "1149", "1149", "463", "0", "0", "0.00"]]

    runtime = _docker(
        "exec",
        "de-demo-iceberg-medallion",
        "sh",
        "-c",
        'printf \'%s|%s|%s\' "$SILVER_MODE" "$GOLD_SOURCE" "$SHADOW_COMPARE"',
    )
    assert runtime == "b2|persisted_silver|1"
