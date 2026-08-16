"""Airflow DAG validation (marked `airflow`; requires the airflow container).

These tests load the DagBag inside the de-demo-airflow container (Airflow 3.3.1)
via `docker exec -i ... python -`, then assert on the dumped structure here on
the host. They are excluded from the default fast run (see pytest.ini); run with
`pytest tests/test_dags.py -m airflow`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

CONTAINER = "de-demo-airflow"
DUMP_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dump_dag_structure.py"

MAINTENANCE_DAG = "lakehouse_maintenance"
EXPECTED_TASKS = {
    "maintain_table",
}
EXPECTED_UPSTREAM = {
    "maintain_table": [],
}
EXPECTED_TABLES = [
    ["bronze", "orders"],
    ["silver", "orders_clean"],
    ["gold", "orders_daily_metrics"],
]
INGESTION_DAG = "warehouse_orders_ingestion"
MARTS_DAG = "warehouse_marts_validation"
DBT_SEMANTIC_DAG = "lakehouse_dbt_semantic"
CORE_ORDERS_URI = "postgres://de-demo-postgres:5432/dwh/core/orders"
INGESTION_UPSTREAM = {
    "staging.load_raw_csv_to_stg": [],
    "staging.validate_staging": ["staging.load_raw_csv_to_stg"],
    "core.rebuild_core": ["staging.validate_staging"],
    "core.validate_core": ["core.rebuild_core"],
    "core.publish_core_assets": ["core.validate_core"],
}

pytestmark = pytest.mark.airflow


@pytest.fixture(scope="module")
def dag_structure() -> dict:
    res = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python", "-"],
        input=DUMP_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if res.returncode != 0:
        raise RuntimeError(f"docker exec failed rc={res.returncode}: {res.stderr}")
    for line in reversed(res.stdout.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise ValueError(f"no JSON payload in docker exec output: {res.stdout[:200]!r}")


def test_dagbag_has_no_import_errors(dag_structure: dict) -> None:
    assert dag_structure["import_errors"] == {}


def test_lakehouse_maintenance_dag_exists(dag_structure: dict) -> None:
    assert MAINTENANCE_DAG in dag_structure["dags"]


def test_maintenance_dag_task_ids(dag_structure: dict) -> None:
    tasks = dag_structure["dags"][MAINTENANCE_DAG]["tasks"]
    assert set(tasks) == EXPECTED_TASKS


def test_maintenance_dag_dependencies(dag_structure: dict) -> None:
    tasks = dag_structure["dags"][MAINTENANCE_DAG]["tasks"]
    assert tasks == EXPECTED_UPSTREAM


def test_maintenance_dag_schedule(dag_structure: dict) -> None:
    dag = dag_structure["dags"][MAINTENANCE_DAG]
    assert dag["schedule"] == "0 * * * *"
    assert dag["catchup"] is False
    assert dag["max_active_runs"] == 1


def test_maintenance_dag_retries_and_timeout(dag_structure: dict) -> None:
    dag = dag_structure["dags"][MAINTENANCE_DAG]
    assert dag["default_retries"] == 0
    assert dag["execution_timeout"] == "0:15:00"


def test_maintenance_dag_ui_metadata_and_mapping(dag_structure: dict) -> None:
    dag = dag_structure["dags"][MAINTENANCE_DAG]
    assert dag["display_name"] == "Lakehouse Table Maintenance"
    assert dag["description"]
    assert dag["has_doc_md"] is True
    assert dag["mapped_tasks"] == ["maintain_table"]
    assert dag["map_index_templates"] == {"maintain_table": "{{ table_name }}"}
    assert dag["task_max_active_tis_per_dagrun"]["maintain_table"] == 1


def test_maintenance_tables_config_is_sane(dag_structure: dict) -> None:
    cfg = dag_structure["maintenance_config"]
    assert cfg["MAINTENANCE_TABLES"] == EXPECTED_TABLES
    assert cfg["RETAIN_LAST"] >= 1
    assert cfg["RETENTION"].strip()
    assert cfg["RECOVERY_HORIZON"].strip()
    assert cfg["RECOVERY_SAFETY_MARGIN"].strip()
    assert cfg["RETENTION_CONTRACT"]["retention_seconds"] > (
        cfg["RETENTION_CONTRACT"]["recovery_horizon_seconds"]
        + cfg["RETENTION_CONTRACT"]["safety_margin_seconds"]
    )
    assert cfg["FILE_SIZE_THRESHOLD"].strip()


def test_warehouse_split_replaces_combined_dag(dag_structure: dict) -> None:
    dags = dag_structure["dags"]
    assert "demo_core_marts_pipeline" not in dags
    assert {INGESTION_DAG, MARTS_DAG} <= dags.keys()


def test_lakehouse_dbt_cosmos_dag_exists(dag_structure: dict) -> None:
    dag = dag_structure["dags"][DBT_SEMANTIC_DAG]
    assert dag["display_name"] == "Lakehouse · dbt Semantic"
    assert dag["description"]
    assert dag["owner"] == "data-platform"
    assert dag["schedule"] == "None"
    assert dag["catchup"] is False
    assert dag["max_active_runs"] == 1
    assert dag["tags"] == sorted(
        [
            "domain:orders",
            "layer:semantic",
            "type:dbt",
            "owner:data-platform",
            "criticality:high",
        ]
    )


def test_orders_ingestion_contract(dag_structure: dict) -> None:
    dag = dag_structure["dags"][INGESTION_DAG]
    assert dag["display_name"] == "Warehouse · Orders Ingestion"
    assert dag["description"]
    assert dag["has_doc_md"] is True
    assert dag["schedule"] == "None"
    assert dag["scheduled_asset_uris"] == []
    assert dag["max_active_runs"] == 1
    assert dag["dagrun_timeout"] == "0:30:00"
    assert dag["default_retries"] == 0
    assert dag["execution_timeout"] == "0:15:00"
    assert dag["owner"] == "data-platform"
    assert dag["tags"] == sorted(
        [
            "domain:orders",
            "layer:core",
            "type:batch",
            "trigger:manual",
            "owner:data-platform",
            "criticality:high",
        ]
    )
    assert dag["tasks"] == INGESTION_UPSTREAM
    assert dag["task_groups"] == {
        "staging.load_raw_csv_to_stg": "staging",
        "staging.validate_staging": "staging",
        "core.rebuild_core": "core",
        "core.validate_core": "core",
        "core.publish_core_assets": "core",
    }
    assert dag["task_assets"] == {
        "staging.load_raw_csv_to_stg": {"inlets": 4, "outlets": 4},
        "staging.validate_staging": {"inlets": 4, "outlets": 0},
        "core.rebuild_core": {"inlets": 4, "outlets": 0},
        "core.validate_core": {"inlets": 0, "outlets": 0},
        "core.publish_core_assets": {"inlets": 0, "outlets": 2},
    }


def test_marts_validation_contract(dag_structure: dict) -> None:
    dag = dag_structure["dags"][MARTS_DAG]
    assert dag["display_name"] == "Warehouse · dbt Marts Validation & Publication"
    assert dag["description"]
    assert dag["has_doc_md"] is True
    assert dag["scheduled_asset_uris"] == [CORE_ORDERS_URI]
    assert dag["max_active_runs"] == 1
    assert dag["dagrun_timeout"] == "0:45:00"
    assert dag["default_retries"] == 0
    assert dag["execution_timeout"] == "None"
    assert dag["owner"] == "data-platform"
    assert dag["tags"] == sorted(
        [
            "domain:orders",
            "layer:marts",
            "type:dbt",
            "trigger:asset",
            "owner:data-platform",
            "criticality:high",
        ]
    )
    tasks = dag["tasks"]
    assert {
        "dbt_warehouse.dbt_producer_watcher",
        "dbt_warehouse.dbt_producer_watcher_done",
        "generate_dbt_docs",
        "validate_dbt_artifacts",
        "publish_mart_assets",
    } <= tasks.keys()
    assert tasks["generate_dbt_docs"] == [
        "dbt_warehouse.dbt_producer_watcher_done",
        "dbt_warehouse.v_customer_state_daily_run",
        "dbt_warehouse.v_order_items_wide.test",
        "dbt_warehouse.v_reconcile_sales_daily.test",
    ]
    assert tasks["validate_dbt_artifacts"] == ["generate_dbt_docs"]
    assert tasks["publish_mart_assets"] == ["validate_dbt_artifacts"]
    assert {
        task_id: assets
        for task_id, assets in dag["task_assets"].items()
        if task_id in {"publish_mart_assets"}
    } == {"publish_mart_assets": {"inlets": 1, "outlets": 5}}
