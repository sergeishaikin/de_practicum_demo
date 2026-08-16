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
from decimal import Decimal
from types import SimpleNamespace
from airflow.models import DagBag

case = __CASE__
sys.path.insert(0, "/opt/airflow/dags")
bag = DagBag(dag_folder="/opt/airflow/dags")
maintenance = bag.dags["lakehouse_maintenance"].task_dict["maintain_table"].python_callable
ingestion = bag.dags["warehouse_orders_ingestion"].task_dict
marts = bag.dags["warehouse_marts_validation"].task_dict
staging = ingestion["staging.validate_staging"].python_callable
core_ready = ingestion["core.validate_core"].python_callable
core_publish = ingestion["core.publish_core_assets"].python_callable
marts_ready = marts["quality.validate_marts"].python_callable
payment = marts["quality.check_payment_reconcile"].python_callable
marts_publish = marts["publication.publish_mart_assets"].python_callable

class Cursor:
    def __init__(self, conn): self.conn = conn
    def execute(self, sql):
        operation = next((name for name in ("optimize", "expire_snapshots", "remove_orphan_files") if name in sql), None)
        if operation:
            self.conn.operations.append(operation)
            if self.conn.fail_on == operation:
                raise RuntimeError(f"boom:{operation}")
        if self.conn.fail_query and self.conn.fail_query in sql:
            raise RuntimeError(f"query failed:{self.conn.fail_query}")
    def fetchone(self):
        if self.conn.payment_values is not None:
            return self.conn.payment_values
        return (self.conn.counts.pop(0),)
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass

class Connection:
    def __init__(self, fail_on=None, counts=None, fail_query=None, payment_values=None):
        self.fail_on = fail_on
        self.operations = []
        self.commits = 0
        self.counts = list(counts or [])
        self.fail_query = fail_query
        self.payment_values = payment_values
    def cursor(self): return Cursor(self)
    def commit(self): self.commits += 1
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass

def metadata_rows(values):
    return sorted(
        [{"uri": value.asset.uri, "extra": value.extra} for value in values],
        key=lambda item: item["uri"],
    )

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
        returned = maintenance({"schema": "silver", "table": "orders_clean"}, "bdd-maintenance-run")
    except RuntimeError as exc:
        error = str(exc)
    result.update(operations=conn.operations, commits=conn.commits, audits=audits, error=error, returned=returned)
elif case.startswith("staging"):
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
    task_globals["_connect"] = lambda: Connection(counts=counts)
    error = None
    try:
        staging()
    except Exception as exc:
        error = str(exc)
    result.update(error=error)
elif case.startswith("core_"):
    task_globals = core_ready.__globals__
    task_globals["_connect"] = lambda: Connection(
        counts=[0, 0],
        fail_query="core.order_items" if case == "core_failure" else None,
    )
    error = None
    metadata = []
    counts = None
    try:
        counts = core_ready()
        metadata = metadata_rows(core_publish(counts))
    except Exception as exc:
        error = str(exc)
    result.update(error=error, counts=counts, metadata=metadata)
elif case == "marts_provenance":
    task_globals = marts_ready.__globals__
    task_globals["_connect"] = lambda: Connection(counts=[10, 20, 30, 40])
    asset = task_globals["CORE_ORDERS_ASSET"]
    event = SimpleNamespace(
        source_dag_run=SimpleNamespace(
            dag_id="warehouse_orders_ingestion",
            run_id="manual__bdd-ingestion",
        )
    )
    state = marts_ready({asset: [event]})
    result.update(state=state)
elif case == "marts_ambiguous_provenance":
    task_globals = marts_ready.__globals__
    task_globals["_connect"] = lambda: Connection(counts=[10, 20, 30, 40])
    asset = task_globals["CORE_ORDERS_ASSET"]
    events = [
        SimpleNamespace(
            source_dag_run=SimpleNamespace(
                dag_id="warehouse_orders_ingestion",
                run_id=run_id,
            )
        )
        for run_id in ("manual__bdd-ingestion-a", "manual__bdd-ingestion-b")
    ]
    error = None
    try:
        marts_ready({asset: events})
    except Exception as exc:
        error = str(exc)
    result.update(error=error)
elif case in {"payment_mismatch", "payment_match"}:
    task_globals = payment.__globals__
    task_globals["_connect"] = lambda: Connection(
        payment_values=(
            (Decimal("10.00"), Decimal("9.00"))
            if case == "payment_mismatch"
            else (Decimal("10.00"), Decimal("10.00"))
        )
    )
    state = {
        "ingestion_run_id": "manual__bdd-ingestion",
        "row_counts": {table: i for i, table in enumerate(task_globals["MART_TABLES"], start=1)},
    }
    error = None
    metadata = []
    try:
        payment()
        metadata = metadata_rows(marts_publish(state))
    except Exception as exc:
        error = str(exc)
    result.update(error=error, metadata=metadata)

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


@given("queryable core tables with zero rows")
def core_zero(context: dict) -> None:
    _select_case(context, "core_zero")


@given("a core table that cannot be queried")
def core_failure(context: dict) -> None:
    _select_case(context, "core_failure")


@given("a core orders event from a successful ingestion DagRun")
def marts_provenance(context: dict) -> None:
    _select_case(context, "marts_provenance")


@given("two core orders events from different ingestion DagRuns")
def marts_ambiguous_provenance(context: dict) -> None:
    _select_case(context, "marts_ambiguous_provenance")


@given("marts readiness followed by a payment mismatch")
def payment_mismatch(context: dict) -> None:
    _select_case(context, "payment_mismatch")


@given("marts readiness followed by matching payments")
def payment_match(context: dict) -> None:
    _select_case(context, "payment_match")


@when("the actual maintenance task callable runs in Airflow")
@when("the actual staging validation task callable runs in Airflow")
@when("the actual core readiness and publisher callables run in Airflow")
@when("the actual marts readiness callable runs in Airflow")
@when("the actual marts quality and publisher callables run in Airflow")
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


@then("core readiness succeeds and both row counts are published")
def core_zero_published(context: dict) -> None:
    result = context["result"]
    assert result["error"] is None
    assert result["counts"] == {"core.orders": 0, "core.order_items": 0}
    assert [row["extra"] for row in result["metadata"]] == [
        {"row_count": 0},
        {"row_count": 0},
    ]


@then("core readiness fails and no core metadata is published")
def core_failure_not_published(context: dict) -> None:
    result = context["result"]
    assert "query failed:core.order_items" in result["error"]
    assert result["metadata"] == []


@then("marts readiness returns the source ingestion run id")
def source_provenance_returned(context: dict) -> None:
    state = context["result"]["state"]
    assert state["ingestion_run_id"] == "manual__bdd-ingestion"
    assert state["row_counts"] == {
        "marts.v_order_items_wide": 10,
        "marts.v_sales_daily": 20,
        "marts.v_customer_state_daily": 30,
        "marts.v_reconcile_sales_daily": 40,
    }


@then("marts readiness rejects ambiguous source provenance")
def ambiguous_source_provenance_rejected(context: dict) -> None:
    assert "Expected exactly one core.orders Asset event" in context["result"]["error"]


@then("payment reconciliation fails and no mart metadata is published")
def payment_failure_not_published(context: dict) -> None:
    result = context["result"]
    assert "Payment reconciliation failed" in result["error"]
    assert result["metadata"] == []


@then("payment reconciliation succeeds and all mart metadata is published")
def payment_success_published(context: dict) -> None:
    result = context["result"]
    assert result["error"] is None
    assert len(result["metadata"]) == 4
