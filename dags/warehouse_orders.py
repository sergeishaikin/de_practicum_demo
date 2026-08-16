from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import psycopg2

from airflow.sdk import Asset, Metadata, TaskGroup, dag, task
from airflow.sdk.exceptions import AirflowException


PROJECT_DIR = Path("/opt/airflow/project")
DATA_DIR = PROJECT_DIR / "data" / "raw"
SQL_DIR = PROJECT_DIR / "db" / "pipeline_sql"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AirflowException(
            f"Required Airflow environment variable is missing: {name}"
        )
    return value


DWH_CONN = {
    "host": os.getenv("DWH_HOST", "de-demo-postgres"),
    "port": int(os.getenv("DWH_PORT", "5432")),
    "dbname": os.getenv("DWH_DB", "dwh"),
    "user": os.getenv("DWH_USER", "app"),
    "password": _required_env("DWH_PASSWORD"),
}

STG_LOADS = [
    (
        "stg.orders",
        "olist_orders_dataset.csv",
        [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
            "ingest_date",
        ],
    ),
    (
        "stg.order_items",
        "olist_order_items_dataset.csv",
        [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
            "ingest_date",
        ],
    ),
    (
        "stg.order_payments",
        "olist_order_payments_dataset.csv",
        [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
            "ingest_date",
        ],
    ),
    (
        "stg.customers",
        "olist_customers_dataset.csv",
        [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
            "ingest_date",
        ],
    ),
]

MART_TABLES = [
    "marts.v_order_items_wide",
    "marts.v_sales_daily",
    "marts.v_customer_state_daily",
    "marts.v_reconcile_sales_daily",
]

INGESTION_DAG_DOC = """
## Warehouse · Orders Ingestion

Manual batch boundary for the four Olist CSV inputs. The workflow loads and
validates staging, executes the unchanged transactional core rebuild, then
performs a read-only queryability/count check for `core.orders` and
`core.order_items`.

Only the final `publish_core_assets` task emits core Asset events. A failed or
skipped load, validation, rebuild, or readiness task therefore produces no
scheduling event for the downstream marts workflow. Event metadata contains
only the published table's row count.
"""

MARTS_DAG_DOC = """
## Warehouse · Marts Validation & Publication

Runs after a successful `core.orders` Asset update. This workflow keeps marts
as PostgreSQL views: it checks that all four views are queryable, applies the
existing payment reconciliation, publishes mart Asset events, and writes the
existing idempotent pipeline audit.

The audit keeps this DagRun's ID as `marts.pipeline_runs.run_id` and records
the source ingestion DagRun from native Asset-event provenance in
`ingestion_run_id`. Missing or invalid provenance fails closed.
"""

DAG_DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 0,
    "execution_timeout": timedelta(minutes=15),
}

RAW_CSV_ASSETS = [
    Asset(f"file://{DATA_DIR / csv_name}", group="Raw CSV")
    for _, csv_name, _ in STG_LOADS
]


def _postgres_asset(name: str, *, group: str) -> Asset:
    return Asset(
        "postgres://"
        f"{DWH_CONN['host']}:{DWH_CONN['port']}/{DWH_CONN['dbname']}/{name}",
        group=group,
    )


STG_ASSETS = [
    _postgres_asset(table.replace(".", "/"), group="PostgreSQL · Staging")
    for table, _, _ in STG_LOADS
]
CORE_ORDERS_ASSET = _postgres_asset("core/orders", group="PostgreSQL · Core")
CORE_ORDER_ITEMS_ASSET = _postgres_asset("core/order_items", group="PostgreSQL · Core")
CORE_ASSETS = [CORE_ORDERS_ASSET, CORE_ORDER_ITEMS_ASSET]
MART_ASSETS = [
    _postgres_asset(table.replace(".", "/"), group="PostgreSQL · Marts")
    for table in MART_TABLES
]
PIPELINE_AUDIT_ASSET = _postgres_asset(
    "marts/pipeline_runs", group="PostgreSQL · Audit"
)


def _connect():
    return psycopg2.connect(**DWH_CONN)


def _execute_sql_file(conn, path: Path) -> None:
    with path.open("r", encoding="utf-8") as sql_file:
        sql = sql_file.read()

    with conn.cursor() as cur:
        cur.execute(sql)


def _copy_csv(conn, table: str, csv_name: str, columns: list[str]) -> None:
    csv_path = DATA_DIR / csv_name
    if not csv_path.exists():
        raise AirflowException(f"Missing raw CSV file: {csv_path}")

    column_sql = ", ".join(columns)
    copy_sql = f"copy {table} ({column_sql}) from stdin with (format csv, header true)"

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        with conn.cursor() as cur:
            cur.copy_expert(copy_sql, csv_file)


def _csv_data_row_count(csv_name: str) -> int:
    csv_path = DATA_DIR / csv_name
    if not csv_path.exists():
        raise AirflowException(f"Missing raw CSV file: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        records = csv.reader(csv_file)
        next(records, None)
        return sum(1 for _ in records)


def _source_ingestion_run_id(triggering_asset_events) -> str:
    if not triggering_asset_events:
        raise AirflowException("Missing triggering core.orders Asset event")

    matching_event_lists = [
        events
        for asset, events in triggering_asset_events.items()
        if getattr(asset, "uri", None) == CORE_ORDERS_ASSET.uri
    ]
    if len(matching_event_lists) != 1 or len(matching_event_lists[0]) != 1:
        raise AirflowException(
            "Expected exactly one core.orders Asset event for this DagRun"
        )

    event = matching_event_lists[0][0]
    source_dag_run = getattr(event, "source_dag_run", None)
    source_dag_id = getattr(source_dag_run, "dag_id", None)
    source_run_id = getattr(source_dag_run, "run_id", None)
    if source_dag_id != "warehouse_orders_ingestion" or not source_run_id:
        raise AirflowException(
            "Invalid core.orders Asset provenance: "
            f"source_dag_id={source_dag_id!r} source_run_id={source_run_id!r}"
        )
    return str(source_run_id)


@dag(
    dag_id="warehouse_orders_ingestion",
    dag_display_name="Warehouse · Orders Ingestion",
    description="Manually load and validate Olist staging, then rebuild and publish PostgreSQL core tables.",
    doc_md=INGESTION_DAG_DOC,
    default_args=DAG_DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    tags=[
        "domain:orders",
        "layer:core",
        "type:batch",
        "trigger:manual",
        "owner:data-platform",
        "criticality:high",
    ],
)
def warehouse_orders_ingestion():
    with TaskGroup(
        group_id="staging",
        group_display_name="Staging Load & Validation",
        tooltip="Load all four CSV inputs and require exact non-empty parity.",
    ):

        @task(inlets=RAW_CSV_ASSETS, outlets=STG_ASSETS)
        def load_raw_csv_to_stg() -> None:
            with _connect() as conn:
                _execute_sql_file(conn, SQL_DIR / "00_truncate_stg.sql")
                for table, csv_name, columns in STG_LOADS:
                    _copy_csv(conn, table, csv_name, columns)

        @task(inlets=STG_ASSETS)
        def validate_staging() -> None:
            mismatches = []
            with _connect() as conn:
                for table, csv_name, _ in STG_LOADS:
                    csv_count = _csv_data_row_count(csv_name)
                    with conn.cursor() as cur:
                        cur.execute(f"select count(*) from {table}")
                        staging_count = int(cur.fetchone()[0])
                    if (
                        csv_count <= 0
                        or staging_count <= 0
                        or csv_count != staging_count
                    ):
                        mismatches.append(
                            f"table={table} file={csv_name} "
                            f"csv_count={csv_count} staging_count={staging_count}"
                        )

            if mismatches:
                raise AirflowException(
                    "Staging row-count validation failed: " + "; ".join(mismatches)
                )

        load_stg = load_raw_csv_to_stg()
        staging_check = validate_staging()
        load_stg >> staging_check

    with TaskGroup(
        group_id="core",
        group_display_name="Core Rebuild & Publication",
        tooltip="Run the unchanged core transaction, verify queryability, and publish Assets.",
    ):

        @task(inlets=STG_ASSETS)
        def rebuild_core() -> None:
            with _connect() as conn:
                _execute_sql_file(conn, SQL_DIR / "10_rebuild_core.sql")

        @task
        def validate_core() -> dict[str, int]:
            counts: dict[str, int] = {}
            with _connect() as conn:
                for table in ("core.orders", "core.order_items"):
                    with conn.cursor() as cur:
                        cur.execute(f"select count(*) from {table}")
                        counts[table] = int(cur.fetchone()[0])
            return counts

        @task(outlets=CORE_ASSETS)
        def publish_core_assets(counts: dict[str, int]) -> Iterator[Metadata]:
            yield Metadata(CORE_ORDERS_ASSET, {"row_count": int(counts["core.orders"])})
            yield Metadata(
                CORE_ORDER_ITEMS_ASSET,
                {"row_count": int(counts["core.order_items"])},
            )

        rebuild = rebuild_core()
        core_counts = validate_core()
        publish_core = publish_core_assets(core_counts)
        rebuild >> core_counts >> publish_core

    staging_check >> rebuild


@dag(
    dag_id="warehouse_marts_validation",
    dag_display_name="Warehouse · Marts Validation & Publication",
    description="Validate PostgreSQL mart views after a core.orders Asset update, publish marts, and audit provenance.",
    doc_md=MARTS_DAG_DOC,
    default_args=DAG_DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule=[CORE_ORDERS_ASSET],
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    tags=[
        "domain:orders",
        "layer:marts",
        "type:batch",
        "trigger:asset",
        "owner:data-platform",
        "criticality:high",
    ],
)
def warehouse_marts_validation():
    with TaskGroup(
        group_id="quality",
        group_display_name="Marts Readiness & Quality",
        tooltip="Resolve ingestion provenance and apply existing read-only quality gates.",
    ):

        @task(inlets=[CORE_ORDERS_ASSET])
        def validate_marts(triggering_asset_events=None) -> dict:
            ingestion_run_id = _source_ingestion_run_id(triggering_asset_events)
            counts: dict[str, int] = {}
            with _connect() as conn:
                for table in MART_TABLES:
                    with conn.cursor() as cur:
                        cur.execute(f"select count(*) from {table}")
                        counts[table] = int(cur.fetchone()[0])
            return {"ingestion_run_id": ingestion_run_id, "row_counts": counts}

        @task(inlets=[STG_ASSETS[2], CORE_ORDERS_ASSET])
        def check_payment_reconcile() -> None:
            reconcile_sql = """
            select
                coalesce(
                    (select sum(payment_value)
                     from stg.order_payments),
                    0
                )::numeric(18, 2) as stg_payment_sum,
                coalesce(
                    (select sum(payment_value)
                     from core.orders),
                    0
                )::numeric(18, 2) as core_payment_sum
            """

            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(reconcile_sql)
                    stg_payment_sum, core_payment_sum = cur.fetchone()

            diff = abs(stg_payment_sum - core_payment_sum)
            if diff > Decimal("0.01"):
                raise AirflowException(
                    "Payment reconciliation failed: "
                    f"stg_payment_sum={stg_payment_sum}, "
                    f"core_payment_sum={core_payment_sum}, "
                    f"diff={diff}"
                )

        mart_state = validate_marts()
        payment_check = check_payment_reconcile()
        mart_state >> payment_check

    with TaskGroup(
        group_id="publication",
        group_display_name="Marts Publication & Audit",
        tooltip="Publish validated mart Assets and record downstream/source run provenance.",
    ):

        @task(outlets=MART_ASSETS)
        def publish_mart_assets(mart_state: dict) -> Iterator[Metadata]:
            counts = mart_state["row_counts"]
            for table, asset in zip(MART_TABLES, MART_ASSETS, strict=True):
                yield Metadata(asset, {"row_count": int(counts[table])})

        @task(inlets=MART_ASSETS, outlets=[PIPELINE_AUDIT_ASSET])
        def write_audit(airflow_run_id: str, ingestion_run_id: str) -> None:
            audit_sql = """
            with metrics as (
              select
                (select count(*) from stg.orders)::int as stg_orders,
                (select count(*) from stg.order_items)::int as stg_order_items,
                (select count(*) from core.order_items)::int as core_order_items,
                (select count(*) from marts.v_sales_daily)::int as mart_sales_days,
                (
                  select count(*)::int
                  from (
                    select order_id, order_item_id
                    from marts.v_order_items_wide
                    group by order_id, order_item_id
                    having count(*) > 1
                  ) d
                ) as duplicate_grain_rows,
                (
                  select count(*)::int
                  from marts.v_order_items_wide
                  where order_id is null
                     or order_item_id is null
                     or customer_id is null
                     or product_id is null
                     or seller_id is null
                ) as null_key_rows,
                (
                  select coalesce(max(abs(diff_amount)), 0)::numeric(12, 2)
                  from marts.v_reconcile_sales_daily
                ) as max_reconcile_diff
            )
            insert into marts.pipeline_runs (
              run_id,
              ingestion_run_id,
              run_ts,
              status,
              stg_orders,
              stg_order_items,
              core_order_items,
              mart_sales_days,
              duplicate_grain_rows,
              null_key_rows,
              max_reconcile_diff
            )
            select
              %s,
              %s,
              now(),
              case
                when duplicate_grain_rows = 0
                 and null_key_rows = 0
                 and max_reconcile_diff <= 0.01
                then 'success'
                else 'failed'
              end,
              stg_orders,
              stg_order_items,
              core_order_items,
              mart_sales_days,
              duplicate_grain_rows,
              null_key_rows,
              max_reconcile_diff
            from metrics
            on conflict (run_id) do update set
              ingestion_run_id = excluded.ingestion_run_id,
              run_ts = excluded.run_ts,
              status = excluded.status,
              stg_orders = excluded.stg_orders,
              stg_order_items = excluded.stg_order_items,
              core_order_items = excluded.core_order_items,
              mart_sales_days = excluded.mart_sales_days,
              duplicate_grain_rows = excluded.duplicate_grain_rows,
              null_key_rows = excluded.null_key_rows,
              max_reconcile_diff = excluded.max_reconcile_diff
            returning status, duplicate_grain_rows, null_key_rows, max_reconcile_diff;
            """

            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(audit_sql, (airflow_run_id, ingestion_run_id))
                    status, duplicate_rows, null_rows, max_diff = cur.fetchone()

            if status != "success":
                raise AirflowException(
                    "Audit failed: "
                    f"duplicate_grain_rows={duplicate_rows}, "
                    f"null_key_rows={null_rows}, "
                    f"max_reconcile_diff={max_diff}"
                )

        publish_marts = publish_mart_assets(mart_state)
        audit = write_audit("{{ run_id }}", mart_state["ingestion_run_id"])
        payment_check >> publish_marts >> audit


warehouse_orders_ingestion()
warehouse_marts_validation()
