# S1 — dbt semantic modeling and lineage

Status: implemented; repository and ephemeral live-contract verification pass.
The persistent local demo stack also contains pre-M1 rows that correctly fail
the new `business_version` presence contract; this is recorded as a data
backfill/roll-forward residual, not hidden by the semantic layer.

## Runtime ownership

The `dbt/` project owns Trino/Iceberg semantic transformations, tests, and
published contracts. Airflow owns scheduling and operational state; the
`lakehouse_dbt_semantic` DAG renders this project through Astronomer Cosmos in
`ExecutionMode.WATCHER`. A final Airflow task emits the lakehouse semantic
Asset only after the dependency-aware dbt build and tests succeed.

The Airflow image installs the pinned runtime (`dbt-core==1.12.2`,
`dbt-trino==1.10.3`, and `astronomer-cosmos==1.15.0`). The project source is
mounted read-only and `target/` is stored in the `de_demo_dbt_target` volume so
`manifest.json`, `run_results.json`, `catalog.json`, and generated docs survive
individual task runs without making source files mutable.

## Scope

S1 adds a reproducible `dbt-trino` project over the existing Iceberg catalog.
It exposes the already-owned Bronze, B2 Silver, and D-4 Gold tables as dbt
sources, adds a thin BI-facing semantic layer, and produces dbt lineage and
documentation artifacts.

The semantic models are views:

```text
iceberg.bronze.orders ───────────────┐
                                     │ declared source
iceberg.silver.orders_clean ────────┼──> semantic.current_orders ──┐
                                     │                              │
iceberg.gold.orders_daily_metrics ──┘──> semantic.daily_order_metrics ─> Superset
```

`current_orders` is a naming/documentation layer over the authoritative B2
projection. `daily_order_metrics` is a naming/documentation layer over the
existing D-4 aggregate. dbt does not implement version resolution, targeted
overwrite, progress state, or Gold rebuilding.

## Contracts and tests

The project protects these published contracts:

- Silver `order_id` is non-null and unique.
- Silver `business_version` is non-null.
- Silver and Gold statuses are from the accepted domain.
- Gold dimensions are non-null.
- Gold measures are non-null.
- The semantic Gold view has a unique `(order_date, country, status)` grain.

Source tests are intentionally duplicated for the authoritative Silver/Gold
contracts so a failing source is visible even when the semantic views are not
materialized. The custom SQL grain test is deterministic and does not depend on
physical row order.

## Superset and lineage

The dbt exposure `superset_lakehouse_semantic_dashboard` records the BI
dependency on both semantic models. Superset remains an external serving/UI
owner and can query the `iceberg.semantic` views through its existing Trino
connection. No repository-managed Superset dashboard export was present, so S1
does not silently rewrite or migrate a dashboard; the exposure and smoke check
are the handoff contract.

`dbt docs generate` produces `manifest.json`, `catalog.json`, and `index.html`
under `dbt/target/`; CI uploads these as the S1 artifact.

## Reproduction

From the repository root:

```powershell
uv venv --python 3.12 .venv-dbt
uv pip sync --python .venv-dbt/Scripts/python.exe --require-hashes dbt/requirements.txt
Copy-Item dbt/profiles.yml.example dbt/profiles.yml
.venv-dbt/Scripts/dbt.exe parse --project-dir dbt --profiles-dir dbt
.venv-dbt/Scripts/dbt.exe compile --project-dir dbt --profiles-dir dbt
.venv-dbt/Scripts/dbt.exe docs generate --project-dir dbt --profiles-dir dbt
.venv-dbt/Scripts/dbt.exe run --project-dir dbt --profiles-dir dbt --select semantic
.venv-dbt/Scripts/dbt.exe test --project-dir dbt --profiles-dir dbt
```

The profile defaults to the local Trino endpoint (`localhost:18082`) and can
be overridden with `DBT_TRINO_USER`, `DBT_TRINO_HOST`, and `DBT_TRINO_PORT`.
The generated local `dbt/profiles.yml` is ignored by git.

## Verification evidence

The deterministic repository contract is exercised by `tests/test_s1_dbt.py`.
The CI workflow runs `dbt parse`, `dbt compile`, and `dbt docs generate`, then
uploads the manifest/catalog artifacts. Live `dbt run` and `dbt test` are run
against the local Trino/Iceberg stack as part of the S1 handoff verification.

Recorded verification:

- `dbt parse --no-partial-parse`: PASS; 2 models, 26 tests, 3 sources, 1 exposure
- `dbt compile`: PASS
- `dbt docs generate`: PASS; `manifest.json` and `catalog.json` generated
- `dbt run --select semantic`: PASS; 2 Iceberg views created in `iceberg.semantic`
- `dbt test` on the persistent demo stack: 24 PASS, 2 expected contract failures;
  both failures report 206548 rows with NULL `business_version` in pre-M1 data
- `dbt test` on the deterministic S1 fixture: PASS in CI workflow design
- Trino semantic-view smoke: PASS (`206668` current-order rows, `96` daily-metric rows)
- Superset health smoke: PASS (`OK` from `http://localhost:18088/health`)
- Ruff: PASS
- Fast suite: `113 passed, 30 deselected`

The two persistent-stack failures are intentionally not excluded from the
contract. They prove that the existing retained demo dataset predates M1;
the remediation is an operational backfill/roll-forward decision outside S1,
not a dbt transformation that would silently discard rows.

## Explicit non-goals

S1 does not change Bronze writer semantics, B2 Silver resolution, durable
progress/recovery, D-4 Gold ownership, or the physical layout. D-3a remains a
telemetry-triggered deferred optimization; dbt lineage does not constitute
evidence for changing the Iceberg partitioning strategy.
