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

## Testing layers

The project is tested at three levels, each answering a different question.

**Unit tests** (`models/marts/unit_tests.yml`) — *does the SQL compute the right
thing?* Fixture rows are mocked for every `source()` and `ref()`, so no
warehouse data is involved. They pin the semantics that are easy to break and
invisible in a green production run:

| Unit test | Guards |
|---|---|
| `order_items_wide_keeps_items_without_a_matching_order` | the `LEFT JOIN` to `core.orders`; an inner join would silently drop items |
| `order_items_wide_enriches_every_item_of_its_order` | per-item enrichment across a multi-item order, and NULL payment propagation |
| `sales_daily_counts_orders_distinctly_and_sums_money_per_day` | `COUNT(DISTINCT order_id)` vs `COUNT(*)`, the money sums, and day grouping |
| `reconcile_sales_daily_reports_both_sides_of_the_full_join` | all four `FULL JOIN` branches, both `COALESCE`s, and the sign of `diff_amount` |
| `reconcile_sales_daily_ignores_cross_batch_ingest_dates` | the `ingest_date` predicate that keeps ingestion batches from cross-reconciling |

**Data tests** — *do the real rows satisfy the contract?* Enforced model
contracts cover column shape; `core.orders.order_id` is unique and not null;
`core_order_items_grain_unique` and `tests/order_items_wide_grain.sql` cover the
`(order_id, order_item_id)` grain on both sides of the mart join, which is what
makes fan-out detectable. `tests/mart_reconciliation.sql` and
`tests/payment_reconciliation.sql` assert source-to-mart and staging-to-core
agreement. `tests/customer_state_rolls_up_to_sales_daily.sql` asserts the
cross-model invariant that the state grain sums back to the daily grain
exactly.

**Integration check** — *does the whole chain still line up?* The `ci-pr.yml`
`warehouse-dbt-contract` job seeds `tests/fixtures/warehouse/seed_staging.sql`
(three orders, two days, two customer states, a multi-item order and a
multi-row payment), runs the production `db/pipeline_sql/10_rebuild_core.sql`
rather than a hand-written core insert, runs `dbt build`, then requires
`tests/fixtures/warehouse/assert_marts.sql` to return zero rows. That file
pins the exact expected `core.orders`, `v_sales_daily`,
`v_customer_state_daily`, `v_order_items_wide` and `v_reconcile_sales_daily`
tuples, including `diff_amount = 0` on both days.

`dbt build` runs models, data tests and unit tests together, so the existing CI
job covers all three layers.

The seed is destructive — it truncates `stg.*` and the rebuild truncates
`core.*` — so it aborts if `marts.pipeline_runs` already holds rows. Run it
only against an ephemeral database.

Not adopted, deliberately: SQL linting (no defect here it would have caught,
and it would add a toolchain plus lock churn) and dbt source freshness (the
`stg.*` relations carry no `loaded_at_field`, and ingestion is manual-trigger
by design).

## Schema naming is intentional

`macros/generate_schema_name.sql` returns the model's custom schema verbatim
and discards `target.schema`, which is the opposite of dbt's default
`<target_schema>_<custom_schema>` behaviour and its environment-isolation
advice. That is deliberate here: the marts must keep their legacy relation
names. `dags/warehouse_dbt.py` reads `marts.v_order_items_wide`,
`marts.v_sales_daily` and `marts.v_reconcile_sales_daily` by literal name in
the audit SQL, and publishes Assets whose URIs end in `marts/<view>`; the
Metabase and Superset models point at the same names. Restoring the default
prefix would rename every view and break the audit, the Assets and the BI
layer.

The trade-off is that this project has no per-developer schema isolation: two
targets pointed at the same database write the same `marts.*` relations. The
mitigation is that the project is only ever run against an ephemeral CI
database or the single local `dwh`.

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
