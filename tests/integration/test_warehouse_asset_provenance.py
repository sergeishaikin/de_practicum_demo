"""Integration checks for the additive warehouse provenance migration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
POSTGRES_CONTAINER = "de-demo-postgres"
MIGRATION = ROOT / "db" / "init" / "007_pipeline_runs_ingestion_provenance.sql"


def _psql(sql: str) -> str:
    process = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            POSTGRES_CONTAINER,
            "psql",
            "-XAt",
            "-F",
            "|",
            "--set=ON_ERROR_STOP=1",
            "-U",
            "app",
            "-d",
            "dwh",
        ],
        input=sql,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    return process.stdout.strip()


@pytest.mark.integration
def test_pipeline_runs_provenance_migration_is_idempotent_and_additive() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    _psql(migration)
    _psql(migration)

    schema = _psql(
        """
        select
          (select is_nullable from information_schema.columns
           where table_schema='marts' and table_name='pipeline_runs'
             and column_name='ingestion_run_id'),
          (select count(*) from pg_indexes
           where schemaname='marts' and tablename='pipeline_runs'
             and indexname='idx_pipeline_runs_ingestion_run_id'),
          (select count(*) from pg_indexes
           where schemaname='marts' and tablename='pipeline_runs'
             and indexname='pipeline_runs_pkey'
             and indexdef like '%(run_id)%'),
          (select count(*) from pg_indexes
           where schemaname='marts' and tablename='pipeline_runs'
             and indexname='idx_pipeline_runs_ingestion_run_id'
             and indexdef not like 'CREATE UNIQUE INDEX%');
        """
    )
    assert schema == "YES|1|1|1"

    # `marts` is co-owned: `db/init` owns the audit objects, dbt owns the four
    # `v_*` views. "Additive" therefore means the migration left the *bootstrap*
    # objects intact - the mart views are not in scope here and do not exist yet
    # on a clean stack, because only `dbt build` creates them.
    # The ownership boundary itself is pinned by
    # `test_bootstrap_sql_does_not_define_the_mart_views` and, at runtime, by the
    # catalog assertions in the Metadata profile workflow.
    bootstrap_relations = _psql(
        """
        select relname || ':' || relkind::text
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='marts'
          and relname in ('pipeline_runs','v_smoke_last_run')
        order by relname;
        """
    )
    assert bootstrap_relations.splitlines() == [
        "pipeline_runs:r",
        "v_smoke_last_run:v",
    ]
