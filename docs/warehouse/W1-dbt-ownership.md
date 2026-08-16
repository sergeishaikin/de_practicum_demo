# W1 — Warehouse dbt ownership

Status: implemented; the warehouse mart views and validation contracts are
owned by the dedicated `dbt/warehouse` project.

## Ownership boundary

`warehouse_orders_ingestion` remains responsible for loading the four CSV
inputs and executing the unchanged transactional `db/pipeline_sql/10_rebuild_core.sql`
core rebuild. Its successful `core.orders` Asset is the only schedule for
`warehouse_marts_validation`.

The Asset-triggered DAG uses Astronomer Cosmos 1.15.0 in
`ExecutionMode.WATCHER`. Cosmos renders the warehouse dbt graph and executes
the canonical `dbt build` command. dbt owns the four PostgreSQL mart views:

- `marts.v_order_items_wide`
- `marts.v_sales_daily`
- `marts.v_customer_state_daily`
- `marts.v_reconcile_sales_daily`

The final Airflow task runs only after dbt models and tests succeed. It checks
the legacy audit invariants, writes `marts.pipeline_runs`, and publishes the
four mart Assets plus the audit Asset. Missing or ambiguous core provenance,
dbt failure, artifact failure, or audit failure publishes nothing.

## dbt project and contracts

The project is `dbt/warehouse`, with pinned `dbt-core==1.12.2` and
`dbt-postgres==1.11.0`. PostgreSQL `stg.*` and `core.*` relations are declared
as sources and tagged with their Airflow ownership. The mart views preserve
the existing relation names and SQL semantics. Enforced model contracts cover
the published columns; singular tests cover source-to-mart sales
reconciliation, order-item grain, and staging-to-core payment reconciliation.

Selectors:

- `warehouse_contracts` — tier-1 mart contracts and descendants.
- `warehouse_reconciliation` — reconciliation models and tests.

After each successful build, Cosmos callbacks persist and the DAG validates:
`manifest.json`, `run_results.json`, `catalog.json`, and `index.html` under the
writable runtime sink `/tmp/warehouse_dbt_artifacts`, which also backs the Cosmos
warehouse docs endpoint.

## Reproduction

```powershell
Copy-Item dbt/warehouse/profiles.yml.example dbt/warehouse/profiles.yml
uv venv --python 3.12 .venv-dbt-warehouse
uv pip sync --python .venv-dbt-warehouse/Scripts/python.exe --require-hashes dbt/warehouse/requirements.txt
.venv-dbt-warehouse/Scripts/dbt.exe build --project-dir dbt/warehouse --profiles-dir dbt/warehouse
.venv-dbt-warehouse/Scripts/dbt.exe docs generate --project-dir dbt/warehouse --profiles-dir dbt/warehouse
```

The complete local-stack proof is:

```text
manual warehouse_orders_ingestion
  → successful core.orders Asset
  → warehouse_marts_validation (Cosmos WATCHER / dbt build)
  → dbt models and tests
  → validated artifacts
  → mart Assets + pipeline audit
```

The audit keeps the Airflow Asset-triggered DagRun ID in `run_id` and the
source ingestion DagRun ID in `ingestion_run_id`.
