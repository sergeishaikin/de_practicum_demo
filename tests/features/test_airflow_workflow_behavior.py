"""pytest-bdd steps for the Airflow workflow behavioral contract."""

from __future__ import annotations

import json
import subprocess

import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("airflow_workflow_behavior.feature")

pytestmark = [pytest.mark.bdd, pytest.mark.airflow]

CONTAINER = "de-demo-airflow"

AIRFLOW_CALLABLE_SCRIPT = r"""
import json
import sys
from airflow.models import DagBag

case = __CASE__
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

result = {"case": case}
if case.startswith("maintenance"):
    task_globals = maintenance.__globals__
    task_globals["get_current_context"] = lambda: {}
    audits = []
    task_globals["_upsert_audit"] = lambda *args: audits.append(args)
    task_globals["_snapshot_count"] = lambda conn, schema, table: 7 if not conn.commits else 5
    task_globals["_fresh_snapshot_count"] = lambda *_: 6
    conn = Connection(fail_on="expire_snapshots" if case == "maintenance_failure" else None)
    task_globals["_trino_connect"] = lambda: conn
    error = None
    returned = None
    try:
        returned = maintenance(
            {"schema": "silver", "table": "orders_clean"},
            "bdd-maintenance-run",
        )
    except RuntimeError as exc:
        error = str(exc)
    result.update(
        operations=conn.operations,
        commits=conn.commits,
        audits=audits,
        error=error,
        returned=returned,
    )
else:
    task_globals = staging.__globals__
    task_globals["STG_LOADS"] = [
        ("stg.a", "a", []), ("stg.b", "b", []),
        ("stg.c", "c", []), ("stg.d", "d", []),
    ]
    task_globals["_csv_data_row_count"] = lambda name: {"a": 1, "b": 2, "c": 3, "d": 4}[name]
    counts = {
        "staging_exact": [1, 2, 3, 4],
        "staging_empty": [1, 2, 0, 4],
        "staging_mismatch": [1, 2, 99, 4],
    }[case]
    task_globals["_connect"] = lambda: Connection(staging_counts=counts)
    error = None
    try:
        staging()
    except Exception as exc:
        error = str(exc)
    result.update(error=error)

print(json.dumps(result))
"""


@pytest.fixture
def context() -> dict:
    return {}


def _select_case(context: dict, case: str) -> None:
    context["case"] = case


@given("a maintenance target with successful controlled boundaries")
def maintenance_success(context: dict) -> None:
    _select_case(context, "maintenance_success")


@given("a maintenance target whose snapshot expiry fails")
def maintenance_failure(context: dict) -> None:
    _select_case(context, "maintenance_failure")


@given("four exact non-empty CSV and staging pairs")
def staging_exact(context: dict) -> None:
    _select_case(context, "staging_exact")


@given("one empty staging pair among the four inputs")
def staging_empty(context: dict) -> None:
    _select_case(context, "staging_empty")


@given("one mismatched staging pair among the four inputs")
def staging_mismatch(context: dict) -> None:
    _select_case(context, "staging_mismatch")


@when("the actual maintenance task callable runs in Airflow")
@when("the actual staging validation task callable runs in Airflow")
def run_actual_callable(context: dict) -> None:
    script = AIRFLOW_CALLABLE_SCRIPT.replace("__CASE__", json.dumps(context["case"]))
    proc = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    context["result"] = json.loads(proc.stdout.splitlines()[-1])


@then("maintenance operations run exactly in the required order")
def exact_operation_order(context: dict) -> None:
    assert context["result"]["operations"] == [
        "optimize",
        "expire_snapshots",
        "remove_orphan_files",
    ]
    assert context["result"]["commits"] == 3


@then("an ok maintenance audit is recorded")
def ok_audit(context: dict) -> None:
    assert context["result"]["audits"] == [
        ["bdd-maintenance-run", "silver.orders_clean", 7, 5, "ok"]
    ]


@then("no maintenance operation runs after snapshot expiry")
def no_later_operation(context: dict) -> None:
    assert context["result"]["operations"] == ["optimize", "expire_snapshots"]
    assert context["result"]["commits"] == 1


@then("a failed snapshot expiry audit is recorded")
def failed_audit(context: dict) -> None:
    assert context["result"]["audits"] == [
        [
            "bdd-maintenance-run",
            "silver.orders_clean",
            7,
            6,
            "failed:expire_snapshots",
        ]
    ]


@then("the original maintenance exception is re-raised")
def original_exception(context: dict) -> None:
    assert context["result"]["error"] == "boom:expire_snapshots"


@then("staging validation succeeds")
def staging_accepted(context: dict) -> None:
    assert context["result"]["error"] is None


@then("staging validation fails for the empty pair")
def empty_rejected(context: dict) -> None:
    assert "stg.c" in context["result"]["error"]
    assert "staging_count=0" in context["result"]["error"]


@then("staging validation fails for the mismatched pair")
def mismatch_rejected(context: dict) -> None:
    assert "stg.c" in context["result"]["error"]
    assert "csv_count=3 staging_count=99" in context["result"]["error"]
