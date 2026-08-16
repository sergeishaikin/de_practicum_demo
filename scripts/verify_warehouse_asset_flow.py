"""Prove the exact Airflow warehouse Asset flow with one ingestion trigger.

The verifier fails closed: it never triggers the downstream DAG directly and
never retries an ambiguous source trigger. It writes a receipt only after the
exact source DagRun, core Asset events, asset-triggered downstream DagRun, and
pipeline audit provenance all succeed.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _project_setting(name: str, default: str) -> str:
    """Read non-secret runtime identity from process env or the local .env."""
    if value := os.getenv(name):
        return value
    env_path = ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("'\"")
    return default


INGESTION_DAG = "warehouse_orders_ingestion"
MARTS_DAG = "warehouse_marts_validation"
AIRFLOW_CONTAINER = os.getenv("AIRFLOW_CONTAINER", "de-demo-airflow")
POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", "de-demo-postgres")
DWH_HOST = _project_setting("DWH_HOST", "de-demo-postgres")
DWH_PORT = _project_setting("DWH_PORT", "5432")
DWH_DATABASE = _project_setting("POSTGRES_DB", "dwh")
DWH_USER = _project_setting("POSTGRES_USER", "app")
AIRFLOW_DATABASE = _project_setting("AIRFLOW_DB_NAME", "airflow_meta")
AIRFLOW_USER = _project_setting("AIRFLOW_DB_USER", "airflow")
CORE_ORDERS_URI = f"postgres://{DWH_HOST}:{DWH_PORT}/{DWH_DATABASE}/core/orders"
CORE_ORDER_ITEMS_URI = (
    f"postgres://{DWH_HOST}:{DWH_PORT}/{DWH_DATABASE}/core/order_items"
)
CORE_ASSET_URIS = {CORE_ORDERS_URI, CORE_ORDER_ITEMS_URI}
CORE_PUBLISH_TASK = "core.publish_core_assets"
TIMEOUT_SECONDS = int(os.getenv("VERIFY_TIMEOUT_SECONDS", "300"))
POLL_SECONDS = int(os.getenv("VERIFY_POLL_SECONDS", "5"))
RECEIPT_PATH = Path(
    os.getenv(
        "WAREHOUSE_ASSET_RECEIPT_PATH",
        ROOT / "artifacts" / "phase-02" / "warehouse-asset-flow.json",
    )
)

CSV_FILES = {
    "stg.orders": "olist_orders_dataset.csv",
    "stg.order_items": "olist_order_items_dataset.csv",
    "stg.order_payments": "olist_order_payments_dataset.csv",
    "stg.customers": "olist_customers_dataset.csv",
}


class VerificationError(RuntimeError):
    """A deterministic mismatch that must stop the one-shot verification."""


def _docker(*args: str, input_text: str | None = None, timeout: int = 90) -> str:
    proc = subprocess.run(
        ["docker", *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()


def _airflow(*args: str, timeout: int = 90) -> str:
    return _docker("exec", AIRFLOW_CONTAINER, "airflow", *args, timeout=timeout)


def _psql(
    database: str,
    user: str,
    sql: str,
    **variables: str,
) -> list[list[str]]:
    command = [
        "exec",
        "-i",
        POSTGRES_CONTAINER,
        "psql",
        "-XAt",
        "-F",
        "|",
        "--set=ON_ERROR_STOP=1",
    ]
    for key, value in variables.items():
        command.append(f"--set={key}={value}")
    command.extend(["-U", user, "-d", database])
    output = _docker(*command, input_text=sql)
    return [line.split("|") for line in output.splitlines() if line.strip()]


def make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"warehouse_ingestion_verify_{timestamp}_{uuid.uuid4().hex[:12]}"


def ensure_dags_ready() -> None:
    listed = _airflow("dags", "list", "--output", "plain")
    missing = {INGESTION_DAG, MARTS_DAG} - set(listed.split())
    if missing:
        raise VerificationError(f"DAGs are not parsed: {sorted(missing)}")
    _airflow("dags", "unpause", MARTS_DAG)


def assert_unambiguous_preflight() -> None:
    active = _psql(
        AIRFLOW_DATABASE,
        AIRFLOW_USER,
        """
        select dag_id, run_id, state
        from dag_run
        where dag_id in (:'ingestion_dag', :'marts_dag')
          and state in ('queued', 'running')
        order by dag_id, run_id;
        """,
        ingestion_dag=INGESTION_DAG,
        marts_dag=MARTS_DAG,
    )
    queued_events = _psql(
        AIRFLOW_DATABASE,
        AIRFLOW_USER,
        """
        select a.uri, q.target_dag_id
        from asset_dag_run_queue q
        join asset a on a.id = q.asset_id
        where q.target_dag_id = :'marts_dag';
        """,
        marts_dag=MARTS_DAG,
    )
    if active or queued_events:
        raise VerificationError(
            f"ambiguous preflight: active={active} queued_events={queued_events}"
        )


def trigger_ingestion(run_id: str) -> None:
    _airflow("dags", "trigger", "-r", run_id, INGESTION_DAG)


def dag_run_state(dag_id: str, run_id: str) -> str | None:
    rows = _psql(
        AIRFLOW_DATABASE,
        AIRFLOW_USER,
        """
        select state
        from dag_run
        where dag_id = :'dag_id' and run_id = :'run_id';
        """,
        dag_id=dag_id,
        run_id=run_id,
    )
    if not rows:
        return None
    if len(rows) != 1 or len(rows[0]) != 1:
        raise VerificationError(f"ambiguous DagRun state rows: {rows}")
    return rows[0][0]


def wait_for_success(dag_id: str, run_id: str) -> None:
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        state = dag_run_state(dag_id, run_id)
        if state == "success":
            return
        if state == "failed":
            raise VerificationError(f"{dag_id} run {run_id} failed")
        time.sleep(POLL_SECONDS)
    raise VerificationError(f"timed out waiting for {dag_id} run {run_id}")


def core_event_rows(source_run_id: str) -> list[list[str]]:
    return _psql(
        AIRFLOW_DATABASE,
        AIRFLOW_USER,
        """
        select
          ae.id::text,
          a.uri,
          ae.extra::text,
          ae.source_dag_id,
          ae.source_task_id,
          ae.source_run_id
        from asset_event ae
        join asset a on a.id = ae.asset_id
        where ae.source_dag_id = :'source_dag_id'
          and ae.source_run_id = :'source_run_id'
          and a.uri in (:'orders_uri', :'items_uri')
        order by a.uri;
        """,
        source_dag_id=INGESTION_DAG,
        source_run_id=source_run_id,
        orders_uri=CORE_ORDERS_URI,
        items_uri=CORE_ORDER_ITEMS_URI,
    )


def classify_core_events(
    source_run_id: str,
    rows: list[list[str]],
    expected_counts: dict[str, int],
) -> tuple[bool, str, dict[str, dict]]:
    if len(rows) != 2:
        return False, f"expected 2 core events, found {len(rows)}", {}
    events: dict[str, dict] = {}
    for row in rows:
        if len(row) != 6:
            return False, f"malformed core event row: {row}", {}
        event_id, uri, extra_json, source_dag, source_task, row_source_run = row
        if uri in events:
            return False, f"duplicate core event URI: {uri}", {}
        if source_dag != INGESTION_DAG or source_task != CORE_PUBLISH_TASK:
            return False, f"unexpected producer: {source_dag}.{source_task}", {}
        if row_source_run != source_run_id:
            return False, f"unexpected source run: {row_source_run}", {}
        try:
            extra = json.loads(extra_json)
        except json.JSONDecodeError:
            return False, f"invalid event extra JSON: {extra_json}", {}
        if set(extra) != {"row_count"} or type(extra["row_count"]) is not int:
            return False, f"invalid row-count metadata: {extra}", {}
        if extra["row_count"] < 0:
            return False, f"negative row count: {extra}", {}
        events[uri] = {"event_id": int(event_id), "extra": extra}
    if set(events) != CORE_ASSET_URIS:
        return False, f"unexpected core event URIs: {sorted(events)}", {}
    actual_counts = {uri: event["extra"]["row_count"] for uri, event in events.items()}
    if actual_counts != expected_counts:
        return (
            False,
            f"row-count metadata mismatch: {actual_counts} != {expected_counts}",
            {},
        )
    return True, "exact core events", events


def wait_for_core_events(
    source_run_id: str, expected_counts: dict[str, int]
) -> dict[str, dict]:
    deadline = time.time() + TIMEOUT_SECONDS
    reason = "no events"
    while time.time() < deadline:
        accepted, reason, events = classify_core_events(
            source_run_id, core_event_rows(source_run_id), expected_counts
        )
        if accepted:
            return events
        time.sleep(POLL_SECONDS)
    raise VerificationError(f"core Asset events not accepted: {reason}")


def downstream_rows(event_id: int) -> list[list[str]]:
    return _psql(
        AIRFLOW_DATABASE,
        AIRFLOW_USER,
        """
        select
          dr.run_id,
          dr.state,
          dr.run_type,
          coalesce(dr.triggered_by, ''),
          dae.event_id::text
        from dagrun_asset_event dae
        join dag_run dr on dr.id = dae.dag_run_id
        where dae.event_id = :'event_id'::int
          and dr.dag_id = :'marts_dag'
        order by dr.id;
        """,
        event_id=str(event_id),
        marts_dag=MARTS_DAG,
    )


def classify_downstream(
    event_id: int, rows: list[list[str]]
) -> tuple[bool, str, str | None, str | None]:
    if not rows:
        return False, "no downstream run yet", None, None
    if len(rows) != 1 or len(rows[0]) != 5:
        return False, f"ambiguous downstream rows: {rows}", None, None
    run_id, state, run_type, triggered_by, row_event_id = rows[0]
    if row_event_id != str(event_id):
        return False, f"wrong event association: {row_event_id}", None, None
    if run_type != "asset_triggered":
        return False, f"downstream run is not asset-triggered: {run_type}", None, None
    if triggered_by not in {"ASSET", "TIMETABLE"}:
        return False, f"unexpected downstream trigger: {triggered_by}", None, None
    return True, "exact asset-triggered downstream run", run_id, state


def wait_for_downstream(event_id: int) -> str:
    deadline = time.time() + TIMEOUT_SECONDS
    reason = "no downstream run"
    while time.time() < deadline:
        accepted, reason, run_id, state = classify_downstream(
            event_id, downstream_rows(event_id)
        )
        if accepted and state == "success" and run_id is not None:
            return run_id
        if accepted and state == "failed":
            raise VerificationError(f"downstream run {run_id} failed")
        if not accepted and "ambiguous" in reason:
            raise VerificationError(reason)
        time.sleep(POLL_SECONDS)
    raise VerificationError(f"downstream run not accepted: {reason}")


def task_rows(dag_id: str, run_id: str) -> list[list[str]]:
    return _psql(
        AIRFLOW_DATABASE,
        AIRFLOW_USER,
        """
        select task_id, state, try_number::text, max_tries::text
        from task_instance
        where dag_id = :'dag_id' and run_id = :'run_id'
        order by task_id;
        """,
        dag_id=dag_id,
        run_id=run_id,
    )


def assert_successful_tasks(rows: list[list[str]], expected: set[str]) -> None:
    actual = {row[0] for row in rows}
    if actual != expected:
        raise VerificationError(
            f"task mismatch: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    failed = [row for row in rows if row[1:] != ["success", "1", "0"]]
    if failed:
        raise VerificationError(f"non-single-attempt successful tasks: {failed}")


def audit_rows(downstream_run_id: str) -> list[list[str]]:
    return _psql(
        DWH_DATABASE,
        DWH_USER,
        """
        select run_id, ingestion_run_id, status,
               stg_orders::text, stg_order_items::text,
               core_order_items::text, mart_sales_days::text,
               duplicate_grain_rows::text, null_key_rows::text,
               max_reconcile_diff::text
        from marts.pipeline_runs
        where run_id = :'run_id';
        """,
        run_id=downstream_run_id,
    )


def classify_audit(
    source_run_id: str, downstream_run_id: str, rows: list[list[str]]
) -> tuple[bool, str]:
    if len(rows) != 1 or len(rows[0]) != 10:
        return False, f"expected one audit row, found {rows}"
    row = rows[0]
    if row[0] != downstream_run_id or row[1] != source_run_id:
        return False, f"audit provenance mismatch: {row[:2]}"
    if row[2] != "success":
        return False, f"audit status is {row[2]}"
    if row[7] != "0" or row[8] != "0" or row[9] not in {"0.00", "0"}:
        return False, f"audit quality metrics failed: {row[7:]}"
    return True, "exact successful audit provenance"


def csv_counts() -> dict[str, int]:
    counts = {}
    for table, csv_name in CSV_FILES.items():
        with (ROOT / "data" / "raw" / csv_name).open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = csv.reader(handle)
            next(rows, None)
            counts[table] = sum(1 for _ in rows)
    return counts


def core_counts() -> dict[str, int]:
    rows = _psql(
        DWH_DATABASE,
        DWH_USER,
        "select (select count(*) from core.orders)::text, "
        "(select count(*) from core.order_items)::text;",
    )
    if len(rows) != 1 or len(rows[0]) != 2:
        raise VerificationError(f"cannot read exact core counts: {rows}")
    return {
        CORE_ORDERS_URI: int(rows[0][0]),
        CORE_ORDER_ITEMS_URI: int(rows[0][1]),
    }


def warehouse_snapshot() -> list[list[str]]:
    return _psql(
        DWH_DATABASE,
        DWH_USER,
        """
        select
          (select count(*) from stg.orders)::text,
          (select count(*) from stg.order_items)::text,
          (select count(*) from stg.order_payments)::text,
          (select count(*) from stg.customers)::text,
          (select count(*) from core.orders)::text,
          (select count(*) from core.order_items)::text,
          (select count(*) from marts.v_sales_daily)::text,
          coalesce((select sum(payment_value) from stg.order_payments), 0)::text,
          coalesce((select sum(payment_value) from core.orders), 0)::text,
          coalesce((select max(abs(diff_amount)) from marts.v_reconcile_sales_daily), 0)::text;
        """,
    )


def schema_evidence() -> dict[str, list[list[str]]]:
    return {
        "column": _psql(
            DWH_DATABASE,
            DWH_USER,
            """
            select column_name, is_nullable
            from information_schema.columns
            where table_schema='marts' and table_name='pipeline_runs'
              and column_name='ingestion_run_id';
            """,
        ),
        "index": _psql(
            DWH_DATABASE,
            DWH_USER,
            """
            select indexname, indexdef
            from pg_indexes
            where schemaname='marts' and tablename='pipeline_runs'
              and indexname='idx_pipeline_runs_ingestion_run_id';
            """,
        ),
        "views": _psql(
            DWH_DATABASE,
            DWH_USER,
            """
            select c.relname, c.relkind
            from pg_class c join pg_namespace n on n.oid=c.relnamespace
            where n.nspname='marts'
              and c.relname in ('v_order_items_wide','v_sales_daily',
                                'v_customer_state_daily','v_reconcile_sales_daily')
            order by c.relname;
            """,
        ),
        "historical_nulls": _psql(
            DWH_DATABASE,
            DWH_USER,
            """
            select count(*)::text
            from marts.pipeline_runs
            where ingestion_run_id is null;
            """,
        ),
    }


def main() -> int:
    ensure_dags_ready()
    assert_unambiguous_preflight()
    before = warehouse_snapshot()
    expected_csv_counts = csv_counts()
    if len(before) != 1:
        raise VerificationError(f"missing warehouse baseline: {before}")
    if [int(value) for value in before[0][:4]] != list(expected_csv_counts.values()):
        raise VerificationError(
            f"warehouse baseline does not match CSV inputs: {before[0][:4]}"
        )

    source_run_id = make_run_id()
    print(f"warehouse ingestion verification run_id={source_run_id}", flush=True)
    trigger_ingestion(source_run_id)
    print("triggered ingestion exactly once; downstream will not be triggered manually")

    wait_for_success(INGESTION_DAG, source_run_id)
    expected_core_counts = core_counts()
    events = wait_for_core_events(source_run_id, expected_core_counts)
    orders_event_id = events[CORE_ORDERS_URI]["event_id"]
    downstream_run_id = wait_for_downstream(orders_event_id)

    ingestion_tasks = task_rows(INGESTION_DAG, source_run_id)
    marts_tasks = task_rows(MARTS_DAG, downstream_run_id)
    assert_successful_tasks(
        ingestion_tasks,
        {
            "staging.load_raw_csv_to_stg",
            "staging.validate_staging",
            "core.rebuild_core",
            "core.validate_core",
            "core.publish_core_assets",
        },
    )
    assert_successful_tasks(
        marts_tasks,
        {
            "quality.validate_marts",
            "quality.check_payment_reconcile",
            "publication.publish_mart_assets",
            "publication.write_audit",
        },
    )
    audit = audit_rows(downstream_run_id)
    accepted, reason = classify_audit(source_run_id, downstream_run_id, audit)
    if not accepted:
        raise VerificationError(reason)

    after = warehouse_snapshot()
    if after != before:
        raise VerificationError(
            f"unchanged-input business snapshot drifted: {before} -> {after}"
        )
    schema = schema_evidence()
    if schema["column"] != [["ingestion_run_id", "YES"]]:
        raise VerificationError(f"provenance column mismatch: {schema['column']}")
    if len(schema["index"]) != 1 or "UNIQUE" in schema["index"][0][1].upper():
        raise VerificationError(f"provenance index mismatch: {schema['index']}")
    if len(schema["views"]) != 4 or {row[1] for row in schema["views"]} != {"v"}:
        raise VerificationError(f"marts are not four views: {schema['views']}")

    receipt = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "source": {"dag_id": INGESTION_DAG, "run_id": source_run_id},
        "core_asset_events": events,
        "downstream": {"dag_id": MARTS_DAG, "run_id": downstream_run_id},
        "task_instances": {
            "source": ingestion_tasks,
            "downstream": marts_tasks,
        },
        "pipeline_run": audit[0],
        "csv_counts": expected_csv_counts,
        "core_counts": expected_core_counts,
        "warehouse_snapshot_before": before[0],
        "warehouse_snapshot_after": after[0],
        "schema": schema,
    }
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "OK: manual ingestion -> core.orders AssetEvent -> asset-triggered marts "
        f"run -> pipeline provenance; receipt={RECEIPT_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
