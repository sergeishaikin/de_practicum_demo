from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import psycopg2
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException


PROJECT_DIR = Path("/opt/airflow/project")
DATA_DIR = PROJECT_DIR / "data" / "raw"
SQL_DIR = PROJECT_DIR / "db" / "pipeline_sql"

DWH_CONN = {
    "host": os.getenv("DWH_HOST", "de-demo-postgres"),
    "port": int(os.getenv("DWH_PORT", "5432")),
    "dbname": os.getenv("DWH_DB", "dwh"),
    "user": os.getenv("DWH_USER", "app"),
    "password": os.getenv("DWH_PASSWORD", "app"),
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


@dag(
    dag_id="demo_core_marts_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["demo", "core", "marts"],
)
def demo_core_marts_pipeline():
    @task
    def load_raw_csv_to_stg() -> None:
        with _connect() as conn:
            _execute_sql_file(conn, SQL_DIR / "00_truncate_stg.sql")
            for table, csv_name, columns in STG_LOADS:
                _copy_csv(conn, table, csv_name, columns)

    @task
    def rebuild_core_and_marts() -> None:
        with _connect() as conn:
            _execute_sql_file(conn, SQL_DIR / "10_rebuild_core.sql")

    # Подсказка к заданию 2. Добавь quality gate здесь, между rebuild_core_and_marts и write_audit.
    # TODO 1: создай task check_payment_reconcile через @task.
    # TODO 2: получи суммы из stg.order_payments и core.orders.
    # TODO 3: посчитай diff = abs(stg_payment_sum - core_payment_sum).
    # TODO 4: если diff > 0.01, вызови AirflowException.
    # TODO 5: вставь check_payment_reconcile в цепочку задач ниже.

    @task
    def write_audit(airflow_run_id: str) -> None:
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
                cur.execute(audit_sql, (airflow_run_id,))
                status, duplicate_rows, null_rows, max_diff = cur.fetchone()

        if status != "success":
            raise AirflowException(
                "Audit failed: "
                f"duplicate_grain_rows={duplicate_rows}, "
                f"null_key_rows={null_rows}, "
                f"max_reconcile_diff={max_diff}"
            )

    load_raw_csv_to_stg() >> rebuild_core_and_marts() >> write_audit("{{ run_id }}")


demo_core_marts_pipeline()
