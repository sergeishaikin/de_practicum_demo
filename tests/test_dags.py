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

BEHAVIOR_SCRIPT = r"""
import json
import sys
from airflow.models import DagBag

sys.path.insert(0, "/opt/airflow/dags")
bag = DagBag(dag_folder="/opt/airflow/dags")
maintenance = bag.dags["lakehouse_maintenance"].task_dict["maintain_table"].python_callable
staging = bag.dags["demo_core_marts_pipeline"].task_dict["validate_staging"].python_callable

class Cursor:
    def __init__(self, conn): self.conn = conn
    def execute(self, sql):
        operation = next((name for name in ("optimize", "expire_snapshots", "remove_orphan_files") if name in sql), "snapshot")
        self.conn.operations.append(operation)
        if self.conn.fail_on == operation:
            raise RuntimeError(f"boom:{operation}")
    def fetchone(self): return (self.conn.staging_counts.pop(0),)
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass

class Connection:
    def __init__(self, fail_on=None, staging_counts=None):
        self.fail_on = fail_on
        self.operations = []
        self.commits = 0
        self.staging_counts = list(staging_counts or [])
    def cursor(self): return Cursor(self)
    def commit(self): self.commits += 1
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass

mg = maintenance.__globals__
mg["get_current_context"] = lambda: {}
audits = []
mg["_upsert_audit"] = lambda *args: audits.append(args)
mg["_snapshot_count"] = lambda conn, schema, table: 7 if not conn.commits else 5

success_conn = Connection()
mg["_trino_connect"] = lambda: success_conn
success = maintenance({"schema": "bronze", "table": "orders"}, "run-success")

failure_conn = Connection(fail_on="expire_snapshots")
mg["_trino_connect"] = lambda: failure_conn
mg["_fresh_snapshot_count"] = lambda *_: 6
original_error = None
try:
    maintenance({"schema": "silver", "table": "orders_clean"}, "run-failure")
except RuntimeError as exc:
    original_error = str(exc)

sg = staging.__globals__
sg["_csv_data_row_count"] = lambda name: {"a": 1, "b": 2, "c": 3, "d": 4}[name]
sg["STG_LOADS"] = [("stg.a", "a", []), ("stg.b", "b", []), ("stg.c", "c", []), ("stg.d", "d", [])]
sg["_connect"] = lambda: Connection(staging_counts=[1, 2, 3, 4])
staging()

rejections = []
for counts in ([1, 2, 0, 4], [1, 2, 99, 4]):
    sg["_connect"] = lambda counts=counts: Connection(staging_counts=counts)
    try:
        staging()
    except Exception as exc:
        rejections.append(str(exc))

print(json.dumps({
    "success": success,
    "success_operations": success_conn.operations,
    "success_commits": success_conn.commits,
    "failure_operations": failure_conn.operations,
    "failure_commits": failure_conn.commits,
    "original_error": original_error,
    "audits": audits,
    "staging_rejections": rejections,
}))
"""

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
BATCH_DAG = "demo_core_marts_pipeline"
BATCH_UPSTREAM = {
    "load_raw_csv_to_stg": [],
    "validate_staging": ["load_raw_csv_to_stg"],
    "rebuild_core_and_marts": ["validate_staging"],
    "check_payment_reconcile": ["rebuild_core_and_marts"],
    "write_audit": ["check_payment_reconcile"],
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


def test_demo_core_marts_pipeline_present(dag_structure: dict) -> None:
    dag = dag_structure["dags"][BATCH_DAG]
    assert dag["display_name"] == "Core & Marts Batch Pipeline"
    assert dag["description"]
    assert dag["has_doc_md"] is True
    assert dag["max_active_runs"] == 1
    assert dag["tasks"] == BATCH_UPSTREAM
    assert dag["task_assets"] == {
        "load_raw_csv_to_stg": {"inlets": 4, "outlets": 4},
        "validate_staging": {"inlets": 4, "outlets": 0},
        "rebuild_core_and_marts": {"inlets": 4, "outlets": 6},
        "check_payment_reconcile": {"inlets": 2, "outlets": 0},
        "write_audit": {"inlets": 4, "outlets": 1},
    }


def test_airflow_task_callables_enforce_maintenance_and_staging_behavior() -> None:
    res = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python", "-"],
        input=BEHAVIOR_SCRIPT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, res.stderr
    payload = json.loads(res.stdout.splitlines()[-1])

    assert payload["success"] == {
        "table_name": "bronze.orders",
        "before_snapshots": 7,
        "after_snapshots": 5,
        "status": "ok",
    }
    assert payload["success_operations"] == [
        "optimize",
        "expire_snapshots",
        "remove_orphan_files",
    ]
    assert payload["success_commits"] == 3
    assert payload["failure_operations"] == ["optimize", "expire_snapshots"]
    assert payload["failure_commits"] == 1
    assert payload["original_error"] == "boom:expire_snapshots"
    assert payload["audits"] == [
        ["run-success", "bronze.orders", 7, 5, "ok"],
        ["run-failure", "silver.orders_clean", 7, 6, "failed:expire_snapshots"],
    ]
    assert len(payload["staging_rejections"]) == 2
    assert all("stg.c" in message for message in payload["staging_rejections"])
