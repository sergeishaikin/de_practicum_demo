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
    "capture_before",
    "maintain_table",
    "write_audit",
}
EXPECTED_UPSTREAM = {
    "capture_before": [],
    "maintain_table": ["capture_before"],
    "write_audit": ["maintain_table"],
}
EXPECTED_TABLES = [
    ["bronze", "orders"],
    ["silver", "orders_clean"],
    ["gold", "orders_daily_metrics"],
]

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


def test_demo_core_marts_pipeline_present(dag_structure: dict) -> None:
    dag = dag_structure["dags"]["demo_core_marts_pipeline"]
    assert dag["display_name"] == "Core & Marts Batch Pipeline"
    assert dag["description"]
    assert dag["has_doc_md"] is True
    assert dag["task_assets"] == {
        "load_raw_csv_to_stg": {"inlets": 4, "outlets": 4},
        "rebuild_core_and_marts": {"inlets": 4, "outlets": 6},
        "check_payment_reconcile": {"inlets": 2, "outlets": 0},
        "write_audit": {"inlets": 4, "outlets": 1},
    }
