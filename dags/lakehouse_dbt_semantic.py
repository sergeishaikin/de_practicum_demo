"""Airflow/Cosmos orchestration for the lakehouse semantic dbt project.

The dbt project remains the owner of SQL transformations, tests, and semantic
contracts. Airflow owns scheduling and operational visibility; Cosmos renders
the dbt graph into a TaskGroup and executes one dependency-aware ``dbt build``
in WATCHER mode. The final task publishes an Airflow Asset only after the
Cosmos group succeeds.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import Asset, dag, task
from cosmos import DbtTaskGroup
from cosmos.config import ExecutionConfig, ProfileConfig, ProjectConfig
from cosmos.constants import ExecutionMode


DBT_PROJECT_PATH = Path(
    os.getenv("DBT_PROJECT_PATH", "/opt/airflow/project/dbt")
).resolve()
# Cosmos invokes dbt with ``--profiles-dir``, and dbt only discovers the
# conventional ``profiles.yml`` filename, so Compose mounts the committed
# environment-safe example under that name.  It is mounted *outside* the
# project directory on purpose: a file mount targeting a path inside the
# read-write ./dbt mount makes Docker create that file in the host checkout,
# root-owned and empty.
DBT_PROFILE_PATH = Path(
    os.getenv("DBT_PROFILE_PATH", "/opt/airflow/dbt-profiles/lakehouse/profiles.yml")
).resolve()
LAKEHOUSE_SEMANTIC_ASSET = Asset(
    "trino://de-demo-trino:8080/iceberg/semantic",
    group="Lakehouse · dbt Semantic",
)


@dag(
    dag_id="lakehouse_dbt_semantic",
    dag_display_name="Lakehouse · dbt Semantic",
    description="Build and test the Trino/Iceberg semantic dbt project with Cosmos.",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={"owner": "data-platform", "retries": 0},
    tags=[
        "domain:orders",
        "layer:semantic",
        "type:dbt",
        "owner:data-platform",
        "criticality:high",
    ],
)
def lakehouse_dbt_semantic():
    dbt_build = DbtTaskGroup(
        group_id="dbt_semantic",
        project_config=ProjectConfig(
            dbt_project_path=str(DBT_PROJECT_PATH),
            env_vars={
                "DBT_TRINO_HOST": os.getenv("DBT_TRINO_HOST", "de-demo-trino"),
                "DBT_TRINO_PORT": os.getenv("DBT_TRINO_PORT", "8080"),
                "DBT_TRINO_USER": os.getenv("DBT_TRINO_USER", "admin"),
            },
        ),
        profile_config=ProfileConfig(
            profile_name="lakehouse",
            target_name="dev",
            profiles_yml_filepath=str(DBT_PROFILE_PATH),
        ),
        execution_config=ExecutionConfig(
            execution_mode=ExecutionMode.WATCHER,
            dbt_executable_path=os.getenv("DBT_EXECUTABLE_PATH", "dbt"),
        ),
        operator_args={"install_deps": False},
    )

    @task(outlets=[LAKEHOUSE_SEMANTIC_ASSET])
    def publish_semantic_asset() -> None:
        """Emit the semantic Asset only after dbt models and tests succeed."""

    dbt_build >> publish_semantic_asset()


lakehouse_dbt_semantic()
