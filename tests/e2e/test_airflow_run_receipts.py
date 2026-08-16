"""Read-only verification of immutable Airflow runtime receipts.

Opt in with ``AIRFLOW_RECEIPT_E2E=1``. Run IDs default to the immutable receipt
recorded on 2026-08-15 and may be overridden with ``MAINTENANCE_RECEIPT_RUN_ID``
and ``BATCH_RECEIPT_RUN_ID``. Phase 02 additionally reads its generated Asset
receipt. These tests never trigger or change a DagRun.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

MAINTENANCE_RUN_ID = os.getenv(
    "MAINTENANCE_RECEIPT_RUN_ID",
    "maintenance_verify_20260815T222907391492Z_3be4ca723766",
)
BATCH_RUN_ID = os.getenv(
    "BATCH_RECEIPT_RUN_ID", "batch_verify_20260815T223250865259Z_6c9d0f4252d6"
)

pytestmark = [pytest.mark.e2e, pytest.mark.airflow]
ROOT = Path(__file__).resolve().parents[2]
ASSET_RECEIPT = Path(
    os.getenv(
        "WAREHOUSE_ASSET_RECEIPT_PATH",
        ROOT / "artifacts" / "phase-02" / "warehouse-asset-flow.json",
    )
)


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
    if (
        os.getenv("AIRFLOW_RECEIPT_E2E") != "1"
        and os.getenv("AIRFLOW_ASSET_RECEIPT_E2E") != "1"
    ):
        pytest.skip("set an explicit receipt E2E gate")
    names = set(_docker("ps", "--format", "{{.Names}}").splitlines())
    required = {"de-demo-postgres"}
    if not required <= names:
        pytest.skip(f"receipt services absent: {sorted(required - names)}")


def test_exact_airflow_dagruns_and_single_attempt_task_instances() -> None:
    if os.getenv("AIRFLOW_RECEIPT_E2E") != "1":
        pytest.skip("set AIRFLOW_RECEIPT_E2E=1 for historical receipt verification")
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
    if os.getenv("AIRFLOW_RECEIPT_E2E") != "1":
        pytest.skip("set AIRFLOW_RECEIPT_E2E=1 for historical receipt verification")
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


def test_exact_warehouse_asset_flow_receipt_is_reproducible_read_only() -> None:
    if os.getenv("AIRFLOW_ASSET_RECEIPT_E2E") != "1":
        pytest.skip("set AIRFLOW_ASSET_RECEIPT_E2E=1 for Phase 02 receipt verification")
    receipt = json.loads(ASSET_RECEIPT.read_text(encoding="utf-8"))
    source_run_id = receipt["source"]["run_id"]
    downstream_run_id = receipt["downstream"]["run_id"]

    dag_runs = _psql(
        "airflow_meta",
        "airflow",
        "select dag_id, run_id, state, run_type from dag_run "
        f"where (dag_id='warehouse_orders_ingestion' and run_id='{_quote(source_run_id)}') "
        f"or (dag_id='warehouse_marts_validation' and run_id='{_quote(downstream_run_id)}') "
        "order by dag_id;",
    )
    assert dag_runs == [
        ["warehouse_marts_validation", downstream_run_id, "success", "asset_triggered"],
        ["warehouse_orders_ingestion", source_run_id, "success", "manual"],
    ]

    events = _psql(
        "airflow_meta",
        "airflow",
        "select a.uri, ae.extra::text, ae.source_dag_id, ae.source_task_id, ae.source_run_id "
        "from asset_event ae join asset a on a.id=ae.asset_id "
        f"where ae.source_run_id='{_quote(source_run_id)}' and a.uri like '%/core/%' "
        "order by a.uri;",
    )
    assert len(events) == 2
    assert {row[2] for row in events} == {"warehouse_orders_ingestion"}
    assert {row[3] for row in events} == {"core.publish_core_assets"}
    assert {row[4] for row in events} == {source_run_id}
    assert all(set(json.loads(row[1])) == {"row_count"} for row in events)
    event_counts = {row[0]: json.loads(row[1])["row_count"] for row in events}
    current_core_counts = _psql(
        "dwh",
        "app",
        "select (select count(*) from core.orders), "
        "(select count(*) from core.order_items);",
    )
    assert current_core_counts == [["1000", "1149"]]
    assert event_counts == {
        "postgres://de-demo-postgres:5432/dwh/core/orders": 1000,
        "postgres://de-demo-postgres:5432/dwh/core/order_items": 1149,
    }

    association = _psql(
        "airflow_meta",
        "airflow",
        "select dr.run_id, ae.source_run_id from dagrun_asset_event dae "
        "join dag_run dr on dr.id=dae.dag_run_id "
        "join asset_event ae on ae.id=dae.event_id "
        f"where dr.dag_id='warehouse_marts_validation' and dr.run_id='{_quote(downstream_run_id)}';",
    )
    assert association == [[downstream_run_id, source_run_id]]

    tasks = _psql(
        "airflow_meta",
        "airflow",
        "select dag_id, task_id, state, try_number, max_tries from task_instance "
        f"where (dag_id='warehouse_orders_ingestion' and run_id='{_quote(source_run_id)}') "
        f"or (dag_id='warehouse_marts_validation' and run_id='{_quote(downstream_run_id)}') "
        "order by dag_id, task_id;",
    )
    assert {row[0] for row in tasks} == {
        "warehouse_orders_ingestion",
        "warehouse_marts_validation",
    }
    assert len(tasks) == 9
    assert all(row[2:] == ["success", "1", "0"] for row in tasks)

    audit = _psql(
        "dwh",
        "app",
        "select run_id, ingestion_run_id, status from marts.pipeline_runs "
        f"where run_id='{_quote(downstream_run_id)}';",
    )
    assert audit == [[downstream_run_id, source_run_id, "success"]]

    schema = _psql(
        "dwh",
        "app",
        "select column_name, is_nullable from information_schema.columns "
        "where table_schema='marts' and table_name='pipeline_runs' "
        "and column_name='ingestion_run_id';",
    )
    assert schema == [["ingestion_run_id", "YES"]]

    index = _psql(
        "dwh",
        "app",
        "select count(*) from pg_indexes where schemaname='marts' "
        "and tablename='pipeline_runs' and indexname='idx_pipeline_runs_ingestion_run_id' "
        "and indexdef not like 'CREATE UNIQUE INDEX%';",
    )
    assert index == [["1"]]
    historical = _psql(
        "dwh",
        "app",
        "select run_id, ingestion_run_id from marts.pipeline_runs "
        f"where run_id='{_quote(BATCH_RUN_ID)}' and ingestion_run_id is null;",
    )
    assert historical == [[BATCH_RUN_ID, ""]]

    views = _psql(
        "dwh",
        "app",
        "select c.relname, c.relkind from pg_class c "
        "join pg_namespace n on n.oid=c.relnamespace "
        "where n.nspname='marts' and c.relname in "
        "('v_order_items_wide','v_sales_daily','v_customer_state_daily','v_reconcile_sales_daily') "
        "order by c.relname;",
    )
    assert len(views) == 4
    assert {row[1] for row in views} == {"v"}
