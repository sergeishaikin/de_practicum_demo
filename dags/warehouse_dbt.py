"""First-class PostgreSQL warehouse transformations orchestrated by Cosmos.

The ingestion DAG remains the owner of the staging load and transactional
core rebuild.  This DAG starts only from its successful ``core.orders`` Asset,
then lets dbt own the mart views and their quality contracts.  The final task
is the only publisher of downstream mart Assets and the pipeline audit.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import psycopg2

from airflow.sdk import Asset, Metadata, TriggerRule, dag, get_current_context, task
from airflow.sdk.exceptions import AirflowException
from cosmos import DbtTaskGroup
from cosmos.config import ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import ExecutionMode
from cosmos.operators import DbtDocsOperator

POSTGRES_HOST = os.getenv("DWH_HOST", "de-demo-postgres")
POSTGRES_PORT = int(os.getenv("DWH_PORT", "5432"))
POSTGRES_DB = os.getenv("DWH_DB", "dwh")
POSTGRES_USER = os.getenv("DWH_USER", "app")
POSTGRES_PASSWORD = os.getenv("DWH_PASSWORD")
if not POSTGRES_PASSWORD:
    raise AirflowException(
        "Required Airflow environment variable is missing: DWH_PASSWORD"
    )

DWH_CONN = {
    "host": POSTGRES_HOST,
    "port": POSTGRES_PORT,
    "dbname": POSTGRES_DB,
    "user": POSTGRES_USER,
    "password": POSTGRES_PASSWORD,
}


def _postgres_asset(name: str, *, group: str) -> Asset:
    return Asset(
        f"postgres://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}/{name}",
        group=group,
    )


CORE_ORDERS_ASSET = _postgres_asset("core/orders", group="PostgreSQL · Core")
MART_ASSETS = [
    _postgres_asset(name, group="PostgreSQL · Marts")
    for name in (
        "marts/v_order_items_wide",
        "marts/v_sales_daily",
        "marts/v_customer_state_daily",
        "marts/v_reconcile_sales_daily",
    )
]
PIPELINE_AUDIT_ASSET = _postgres_asset(
    "marts/pipeline_runs", group="PostgreSQL · Audit"
)

WAREHOUSE_DBT_DAG_DOC = """
## Warehouse · dbt Marts Validation & Publication

This Asset-triggered workflow consumes only a successful `core.orders` event
from `warehouse_orders_ingestion`. Cosmos runs the warehouse dbt project in
WATCHER mode (`dbt build`), then generates and validates manifest, run-results,
catalog, and HTML documentation artifacts. The final task writes the existing
`marts.pipeline_runs` provenance row and publishes mart Assets only after every
dbt model and test succeeds.
"""


def _connect():
    return psycopg2.connect(**DWH_CONN)


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


DBT_PROJECT_PATH = Path(
    os.getenv("DBT_WAREHOUSE_PROJECT_PATH", "/opt/airflow/project/dbt/warehouse")
).resolve()
DBT_PROFILE_PATH = DBT_PROJECT_PATH / "profiles.yml"
DBT_EXECUTABLE = os.getenv("DBT_EXECUTABLE_PATH", "dbt")
DBT_ENV = {
    "DBT_POSTGRES_HOST": os.getenv("DBT_POSTGRES_HOST", "de-demo-postgres"),
    "DBT_POSTGRES_PORT": os.getenv("DBT_POSTGRES_PORT", "5432"),
    "DBT_POSTGRES_USER": os.getenv("DBT_POSTGRES_USER", "app"),
    "DBT_POSTGRES_PASSWORD": os.getenv("DBT_POSTGRES_PASSWORD", "change-me"),
    "DBT_POSTGRES_DB": os.getenv("DBT_POSTGRES_DB", "dwh"),
}


def _profile_config() -> ProfileConfig:
    return ProfileConfig(
        profile_name="warehouse",
        target_name="dev",
        profiles_yml_filepath=str(DBT_PROFILE_PATH),
    )


def _project_config() -> ProjectConfig:
    return ProjectConfig(
        dbt_project_path=str(DBT_PROJECT_PATH),
        env_vars=DBT_ENV,
    )


def _audit_and_counts(
    airflow_run_id: str, triggering_asset_events
) -> dict[str, int | str]:
    """Validate the dbt-published views and write the exact legacy audit row."""

    ingestion_run_id = _source_ingestion_run_id(triggering_asset_events)
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
            cur.execute(
                """
                select
                  (select count(*) from stg.orders),
                  (select count(*) from stg.order_items),
                  (select count(*) from core.order_items),
                  (select count(*) from marts.v_sales_daily)
                """
            )
            stg_orders, stg_order_items, core_order_items, mart_sales_days = (
                cur.fetchone()
            )

    if status != "success":
        raise AirflowException(
            "Warehouse dbt audit failed: "
            f"duplicate_grain_rows={duplicate_rows}, "
            f"null_key_rows={null_rows}, max_reconcile_diff={max_diff}"
        )

    return {
        "ingestion_run_id": ingestion_run_id,
        "stg_orders": int(stg_orders),
        "stg_order_items": int(stg_order_items),
        "core_order_items": int(core_order_items),
        "mart_sales_days": int(mart_sales_days),
    }


@dag(
    dag_id="warehouse_marts_validation",
    dag_display_name="Warehouse · dbt Marts Validation & Publication",
    description="Run the PostgreSQL warehouse dbt graph after core publication and publish validated mart Assets.",
    doc_md=WAREHOUSE_DBT_DAG_DOC,
    schedule=[CORE_ORDERS_ASSET],
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={"owner": "data-platform", "retries": 0},
    tags=[
        "domain:orders",
        "layer:marts",
        "type:dbt",
        "trigger:asset",
        "owner:data-platform",
        "criticality:high",
    ],
)
def warehouse_marts_validation():
    dbt_group = DbtTaskGroup(
        group_id="dbt_warehouse",
        project_config=_project_config(),
        profile_config=_profile_config(),
        execution_config=ExecutionConfig(
            execution_mode=ExecutionMode.WATCHER,
            dbt_executable_path=DBT_EXECUTABLE,
        ),
        render_config=RenderConfig(emit_datasets=False),
        operator_args={"install_deps": False},
    )

    generate_docs = DbtDocsOperator(
        task_id="generate_dbt_docs",
        project_dir=str(DBT_PROJECT_PATH),
        profile_config=_profile_config(),
        dbt_executable_path=DBT_EXECUTABLE,
        env=DBT_ENV,
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )
    dbt_producer = next(
        child
        for task_id, child in dbt_group.children.items()
        if task_id.endswith("dbt_producer_watcher")
    )

    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def validate_dbt_artifacts() -> None:
        required = ("manifest.json", "run_results.json", "catalog.json", "index.html")
        missing = [
            name
            for name in required
            if not (DBT_PROJECT_PATH / "target" / name).is_file()
        ]
        if missing:
            raise AirflowException(
                f"Warehouse dbt artifacts missing: {', '.join(missing)}"
            )

    @task(
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
        inlets=[CORE_ORDERS_ASSET],
        outlets=[*MART_ASSETS, PIPELINE_AUDIT_ASSET],
    )
    def publish_mart_assets(triggering_asset_events=None) -> Iterator[Metadata]:
        run_id = str(get_current_context()["dag_run"].run_id)
        state = _audit_and_counts(run_id, triggering_asset_events)
        for asset in MART_ASSETS:
            yield Metadata(asset, {"dbt_project": "warehouse_transform"})
        yield Metadata(
            PIPELINE_AUDIT_ASSET,
            {
                "ingestion_run_id": state["ingestion_run_id"],
                "dbt_project": "warehouse_transform",
            },
        )

    dbt_producer >> generate_docs >> validate_dbt_artifacts() >> publish_mart_assets()


warehouse_marts_validation()
