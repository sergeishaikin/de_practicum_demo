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
import warehouse_dbt
staging = ingestion["staging.validate_staging"].python_callable
core_ready = ingestion["core.validate_core"].python_callable
core_publish = ingestion["core.publish_core_assets"].python_callable

class Cursor:
    def __init__(self, conn): self.conn = conn
    def execute(self, sql, *params):
        operation = next((name for name in ("optimize", "expire_snapshots", "remove_orphan_files") if name in sql), None)
        if operation:
            self.conn.operations.append(operation)
            if self.conn.fail_on == operation:
                raise RuntimeError(f"boom:{operation}")
        if self.conn.fail_query and self.conn.fail_query in sql:
            raise RuntimeError(f"query failed:{self.conn.fail_query}")
    def fetchone(self):
        if hasattr(self.conn, "audit_row"):
            return self.conn.fetchone()
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
    task_globals = warehouse_dbt.__dict__
    asset = task_globals["CORE_ORDERS_ASSET"]
    event = SimpleNamespace(
        source_dag_run=SimpleNamespace(
            dag_id="warehouse_orders_ingestion",
            run_id="manual__bdd-ingestion",
        )
    )
    state = task_globals["_source_ingestion_run_id"]({asset: [event]})
    result.update(state={"ingestion_run_id": state})
elif case == "marts_ambiguous_provenance":
    task_globals = warehouse_dbt.__dict__
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
        task_globals["_source_ingestion_run_id"]({asset: events})
    except Exception as exc:
        error = str(exc)
    result.update(error=error)
elif case in {"payment_mismatch", "payment_match"}:
    task_globals = warehouse_dbt.__dict__
    asset = task_globals["CORE_ORDERS_ASSET"]
    event = SimpleNamespace(source_dag_run=SimpleNamespace(
        dag_id="warehouse_orders_ingestion", run_id="manual__bdd-ingestion"
    ))
    class WarehouseConnection(Connection):
        def __init__(self, audit_row):
            super().__init__(counts=[10, 20, 30, 40])
            self.audit_row = audit_row
        def fetchone(self):
            if self.audit_row is not None:
                row, self.audit_row = self.audit_row, None
                return row
            return tuple(self.counts)
    task_globals["_connect"] = lambda: WarehouseConnection(
        ("failed", 0, 0, 1.00)
        if case == "payment_mismatch"
        else ("success", 0, 0, 0.00)
    )
    error = None
    metadata = []
    try:
        state = task_globals["_audit_and_counts"]("manual__bdd-marts", {asset: [event]})
        metadata = [
            {"uri": output.uri, "extra": {"dbt_project": "warehouse_transform"}}
            for output in [*task_globals["MART_ASSETS"], task_globals["PIPELINE_AUDIT_ASSET"]]
        ]
    except Exception as exc:
        error = str(exc)
    result.update(error=error, metadata=metadata)

elif case in {"publication_blocked_by_failed_validation", "publication_after_recovery"}:
    publisher = bag.dags["warehouse_marts_validation"].task_dict["publish_mart_assets"].python_callable
    # The DagBag loads dags/warehouse_dbt.py as its own module object, so the
    # callable's globals are NOT the separately imported `warehouse_dbt`.
    task_globals = publisher.__globals__
    asset = task_globals["CORE_ORDERS_ASSET"]
    event = SimpleNamespace(source_dag_run=SimpleNamespace(
        dag_id="warehouse_orders_ingestion", run_id="manual__bdd-ingestion"))
    validation = "failed" if case == "publication_blocked_by_failed_validation" else "success"
    task_globals["get_current_context"] = lambda: {
        "dag_run": SimpleNamespace(run_id="asset_triggered__bdd"),
        "ti": SimpleNamespace(dag_id="warehouse_marts_validation"),
    }
    task_globals["_metadata_task_state"] = lambda dag_id, run_id, task_id: validation
    audit_calls = []
    def fake_audit(run_id, events):
        audit_calls.append(run_id)
        return {"ingestion_run_id": "manual__bdd-ingestion", "stg_orders": 1,
                "stg_order_items": 1, "core_order_items": 1, "mart_sales_days": 1}
    task_globals["_audit_and_counts"] = fake_audit
    error = None
    metadata = []
    try:
        metadata = metadata_rows(list(publisher(triggering_asset_events={asset: [event]})))
    except Exception as exc:
        error = str(exc)
    result.update(error=error, metadata=metadata, audit_calls=audit_calls)
elif case == "freshness_failure_stops_certification":
    # The whole chain a stale staging slice must produce. A freshness failure
    # makes dbt_warehouse.dbt_producer_watcher `upstream_failed`; nothing below
    # may then certify or publish.
    validator = bag.dags["warehouse_marts_validation"].task_dict["validate_dbt_artifacts"].python_callable
    publisher = bag.dags["warehouse_marts_validation"].task_dict["publish_mart_assets"].python_callable
    task_globals = publisher.__globals__
    asset = task_globals["CORE_ORDERS_ASSET"]
    event = SimpleNamespace(source_dag_run=SimpleNamespace(
        dag_id="warehouse_orders_ingestion", run_id="manual__bdd-ingestion"))
    task_globals["get_current_context"] = lambda: {
        "dag_run": SimpleNamespace(run_id="asset_triggered__bdd"),
        "ti": SimpleNamespace(dag_id="warehouse_marts_validation"),
    }
    # Exactly the state a failed freshness gate leaves on the Cosmos producer.
    task_globals["_metadata_task_state"] = lambda dag_id, run_id, task_id: "upstream_failed"
    # Count sleeps: without this, a validator that hung and eventually timed out
    # would be indistinguishable from one that raised immediately.
    sleeps = []
    task_globals["time"] = SimpleNamespace(sleep=lambda seconds: sleeps.append(seconds))
    audit_calls = []
    def fake_audit(run_id, events):
        audit_calls.append(run_id)
        return {"ingestion_run_id": "manual__bdd-ingestion", "stg_orders": 1,
                "stg_order_items": 1, "core_order_items": 1, "mart_sales_days": 1}
    task_globals["_audit_and_counts"] = fake_audit
    validator_error = None
    try:
        validator()
    except Exception as exc:
        validator_error = str(exc)
    publisher_error = None
    metadata = []
    try:
        metadata = metadata_rows(list(publisher(triggering_asset_events={asset: [event]})))
    except Exception as exc:
        publisher_error = str(exc)
    result.update(error=validator_error, publisher_error=publisher_error,
                  metadata=metadata, audit_calls=audit_calls, sleeps=sleeps)
elif case == "audit_upsert_is_replay_safe":
    task_globals = warehouse_dbt.__dict__
    asset = task_globals["CORE_ORDERS_ASSET"]
    event = SimpleNamespace(source_dag_run=SimpleNamespace(
        dag_id="warehouse_orders_ingestion", run_id="manual__bdd-ingestion"))
    executed = []
    class RecordingConnection(Connection):
        def __init__(self):
            super().__init__(counts=[10, 20, 30, 40])
            self.audit_row = ("success", 0, 0, 0.00)
            self.executed = executed
        def cursor(self):
            outer = self
            class RecordingCursor(Cursor):
                def execute(self, sql, *params):
                    outer.executed.append(sql)
                    return super().execute(sql, *params)
            return RecordingCursor(self)
        def fetchone(self):
            if self.audit_row is not None:
                row, self.audit_row = self.audit_row, None
                return row
            return tuple(self.counts)
    task_globals["_connect"] = lambda: RecordingConnection()
    error = None
    try:
        task_globals["_audit_and_counts"]("asset_triggered__bdd", {asset: [event]})
    except Exception as exc:
        error = str(exc)
    joined = " ".join(executed).lower()
    result.update(error=error,
                  upsert="on conflict (run_id) do update" in joined,
                  insert_only="insert into marts.pipeline_runs" in joined)
elif case == "replay_truncate_precedes_load":
    loader = ingestion["staging.load_raw_csv_to_stg"].python_callable
    task_globals = loader.__globals__
    order = []
    task_globals["_execute_sql_file"] = lambda conn, path: order.append("sql:" + path.name)
    task_globals["_copy_csv"] = lambda conn, table, csv_name, columns: order.append("copy:" + table)
    task_globals["_connect"] = lambda: Connection()
    error = None
    try:
        loader()
    except Exception as exc:
        error = str(exc)
    result.update(error=error, order=order)
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
@when("the actual marts publisher callable runs in Airflow")
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


@when("the actual marts artifact validation callable runs in Airflow")
def run_actual_validation_callable(context: dict) -> None:
    # A distinct phrase from the publisher step on purpose: this scenario runs
    # validate_dbt_artifacts first and the publisher second, so reusing the
    # publisher phrase would misdescribe what executes.
    run_actual_callable(context)


@then(
    "validation raises on the first poll and publication then refuses without auditing"
)
def assert_freshness_failure_stops_certification(context: dict) -> None:
    result = context["result"]
    # 1. The validator rejects upstream_failed rather than waiting it out.
    assert "prerequisite failed" in (result["error"] or ""), result["error"]
    assert "upstream_failed" in (result["error"] or ""), result["error"]
    # 2. On the FIRST poll. A hang that later timed out would otherwise be
    #    indistinguishable from an immediate raise.
    assert result["sleeps"] == [], result["sleeps"]
    # 3. The publisher then refuses.
    assert "did not succeed before publication" in (
        result["publisher_error"] or ""
    ), result["publisher_error"]
    # 4. The audit was never even attempted, so no row can claim success for a
    #    run built on a stale staging slice.
    assert result["audit_calls"] == []
    # 5. And nothing downstream can be triggered by it.
    assert result["metadata"] == []


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


@then("marts readiness rejects ambiguous source provenance")
def ambiguous_source_provenance_rejected(context: dict) -> None:
    assert "Expected exactly one core.orders Asset event" in context["result"]["error"]


@then("payment reconciliation fails and no mart metadata is published")
def payment_failure_not_published(context: dict) -> None:
    result = context["result"]
    assert "Warehouse dbt audit failed" in result["error"]
    assert result["metadata"] == []


@then("payment reconciliation succeeds and all mart metadata is published")
def payment_success_published(context: dict) -> None:
    result = context["result"]
    assert result["error"] is None
    assert len(result["metadata"]) == 5


@given("a marts run whose dbt artifact validation failed")
def publication_blocked(context: dict) -> None:
    _select_case(context, "publication_blocked_by_failed_validation")


@given("a marts run whose source freshness gate failed")
def freshness_gate_failed(context: dict) -> None:
    _select_case(context, "freshness_failure_stops_certification")


@given("a marts run whose dbt artifact validation succeeded")
def publication_recovered(context: dict) -> None:
    _select_case(context, "publication_after_recovery")


@given("a marts audit for a DagRun id that has already been recorded")
def audit_replay(context: dict) -> None:
    _select_case(context, "audit_upsert_is_replay_safe")


@given("a staging load for a repeated ingestion batch")
def staging_replay(context: dict) -> None:
    _select_case(context, "replay_truncate_precedes_load")


@then("publication is refused, no audit is written and no mart metadata is published")
def assert_publication_blocked(context: dict) -> None:
    result = context["result"]
    assert "did not succeed before publication" in (result["error"] or "")
    # The decisive assertion: the audit was never even attempted, so no row can
    # claim success for a run whose dbt validation failed.
    assert result["audit_calls"] == []
    assert result["metadata"] == []


@then("the audit is written once and all mart metadata is published")
def assert_publication_recovered(context: dict) -> None:
    result = context["result"]
    assert result["error"] is None
    assert result["audit_calls"] == ["asset_triggered__bdd"]
    uris = [row["uri"] for row in result["metadata"]]
    assert len(uris) == 5, uris
    assert any(uri.endswith("marts/pipeline_runs") for uri in uris)


@then("the audit statement upserts on the run id")
def assert_audit_upsert(context: dict) -> None:
    result = context["result"]
    assert result["error"] is None
    assert result["insert_only"], "audit no longer writes marts.pipeline_runs"
    # Without the upsert a retried DagRun would raise on the primary key instead
    # of converging, so the retry could never succeed.
    assert result["upsert"], "audit is not replay-safe on the same run_id"


@then("the truncate runs before any CSV is copied")
def assert_truncate_first(context: dict) -> None:
    result = context["result"]
    assert result["error"] is None
    order = result["order"]
    assert order[0] == "sql:00_truncate_stg.sql", order
    # Everything after the truncate is a copy: staging holds exactly one batch,
    # which is what makes a replayed ingestion idempotent rather than additive.
    assert all(step.startswith("copy:") for step in order[1:]), order
    assert len(order) == 5, order
