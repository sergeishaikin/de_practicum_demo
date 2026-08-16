# Phase 02 Pattern Map

| New/changed surface | Closest repository pattern | Rule to preserve |
|---|---|---|
| `dags/warehouse_orders.py` | `dags/demo_core_marts_pipeline.py`, `dags/lakehouse_maintenance.py` | Airflow SDK decorators, local helpers, `retries=0`, bounded timeouts, parameterized audit values |
| Core event metadata | Existing declared Assets in combined DAG | Shared stable PostgreSQL URIs; terminal task alone owns outlets |
| `db/init/007_pipeline_runs_ingestion_provenance.sql` | idempotent `db/init/*.sql` objects | additive DDL, fresh and existing volume compatibility |
| `scripts/bootstrap_stack.py` | current dependency-aware bootstrap | reuse current execution path; no new runner/service |
| `scripts/verify_warehouse_asset_flow.py` | `scripts/verify_maintenance_dag.py` | unique exact run IDs, parameterized queries, bounded polling, fail closed |
| DagBag tests | `scripts/dump_dag_structure.py` + `tests/test_dags.py` | inspect real Airflow 3.3.1 container, not source text alone |
| Feature tests | existing pytest-bdd feature/steps | Gherkin scenarios execute actual task callables with controlled boundaries |
| Read-only receipt | `tests/e2e/test_airflow_run_receipts.py` | opt-in, exact immutable IDs, no trigger/clear/retry |
| Documentation | README plus architecture/config/development/testing/schema docs | describe actual ownership and commands; retain exercise guidance where possible |
