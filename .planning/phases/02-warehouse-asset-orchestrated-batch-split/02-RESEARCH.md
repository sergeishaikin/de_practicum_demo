# Phase 02 Research: Warehouse Asset-Orchestrated Batch Split

**Date:** 2026-08-16
**Status:** Complete

## Current implementation

`dags/demo_core_marts_pipeline.py` is one manual TaskFlow DAG. It already owns
four-table CSV/staging parity, the transactional core rebuild, payment
reconciliation, and the idempotent `marts.pipeline_runs` audit. The core SQL
rebuilds only `core.orders` and `core.order_items`; the marts are views created
by `db/init/003_core_marts_objects.sql`.

Airflow is pinned to 3.3.1. The existing test stack provides host unit tests,
container DagBag inspection, real Gherkin/pytest-bdd scenarios, stateful
integration tests, and read-only exact-run receipts. No new framework or task
runner is needed.

## Airflow 3.3.1 implementation findings

- A downstream DAG can use `schedule=[CORE_ORDERS_ASSET]` while ingestion keeps
  `schedule=None`.
- Airflow records an Asset update only after the producer task succeeds. A
  failed or skipped producer task therefore cannot schedule the consumer.
- A TaskFlow producer with declared outlets can yield one `Metadata` object per
  Asset. Event `extra` must be JSON serializable and is the correct location
  for each table's integer `row_count`.
- `triggering_asset_events` is injected into a Python task. Each event exposes
  `source_dag_run.run_id`; downstream code should validate the expected Asset
  and producer DAG and fail closed if provenance is absent.
- The two DAG definitions should share the same `Asset` instances in one DAG
  module so URI identity cannot drift.

Primary references:

- https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/asset-scheduling.html
- https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/assets.html

## Recommended DAG shape

Use `dags/warehouse_orders.py` for both DAGs and shared Assets. Remove the old
combined module so only the two new DAG IDs are parsed.

Ingestion:

`staging.load_raw_csv_to_stg -> staging.validate_staging -> core.rebuild_core
-> core.validate_core -> core.publish_core_assets`

Marts:

`quality.validate_marts -> quality.check_payment_reconcile ->
publication.publish_mart_assets -> publication.write_audit`

`validate_marts` can combine read-only view readiness/count collection with
source-Asset provenance resolution, avoiding a decorative provenance task.
The mart publisher yields row-count metadata only after readiness and payment
reconciliation succeed. `write_audit` keeps the current metric SQL and conflict
update, adds `ingestion_run_id`, and still uses current `run_id` as its key.

## Additive PostgreSQL migration

`db/init` runs automatically only for a fresh volume. Update
`004_smoke_objects.sql` to describe the target schema and add an idempotent
`007_pipeline_runs_ingestion_provenance.sql` for existing volumes. Invoke that
migration from the existing `scripts/bootstrap_stack.py` path after PostgreSQL
readiness; do not introduce a migration framework or reset the volume.

The migration must use `ADD COLUMN IF NOT EXISTS`, create a normal index with
`IF NOT EXISTS`, and update `marts.v_smoke_last_run` to expose provenance.
Tests should apply it twice to a temporary schema/table or to the live local
database and prove historical rows remain `NULL`.

## Runtime proof design

Add one existing-style verifier script that:

1. waits for both DAGs to be parsed and unpauses only the downstream DAG;
2. verifies no active/queued run makes the correlation ambiguous;
3. creates and prints one unique ingestion run ID and triggers ingestion once;
4. polls the exact ingestion DagRun to success;
5. queries the exact `core.orders` Asset event and its row-count `extra`;
6. resolves the downstream DagRun scheduled from that event;
7. requires both downstream task states and exact `pipeline_runs` row to be
   successful with `run_id=downstream` and `ingestion_run_id=source`;
8. writes a reproducible JSON receipt without secrets.

Any ambiguous trigger outcome, duplicate candidate downstream run, or missing
source event fails closed and must not be retried with a second ingestion ID.
The committed pytest E2E test remains read-only and validates the recorded
receipt IDs.

## Risks and mitigations

- **False Asset publication:** only the terminal ingestion task declares core
  outlets; rebuild and readiness tasks declare no core outlets.
- **Provenance drift:** validate URI, source DAG ID, and run ID from native
  `AssetEvent`; do not trust event `extra` for identity.
- **Existing-volume drift:** make migration idempotent and part of the current
  bootstrap path.
- **Changed business semantics:** keep `10_rebuild_core.sql`, staging parity,
  payment threshold, and audit metric SQL byte-for-byte or structurally
  unchanged except for provenance columns.
- **Overengineering:** one DAG module, one SQL migration, one verifier, and the
  existing test layers are sufficient.
- **Runtime capacity:** Docker currently reports a very large stateless
  Spark-worker writable layer and PostgreSQL `No space left on device`.
  Recreate only that verified stateless service before live validation; retain
  every named volume.

## Validation Architecture

| Layer | Proof |
|---|---|
| Static/unit | Migration shape/idempotency helpers, verifier classifiers, unchanged SQL and scope fences |
| DagBag | Exact DAG IDs, schedules, metadata, TaskGroups, dependencies, inlets/outlets, retries/timeouts |
| Gherkin BDD | readiness success with zero rows, readiness failure emits no Metadata, provenance source ID, reconciliation blocks publication |
| Migration integration | target column/index, historical NULL preservation, rerun idempotency |
| Runtime integration | real Airflow 3.3.1 import and callable behavior against PostgreSQL |
| Live E2E | one manual ingestion -> exact AssetEvent -> automatic downstream run -> exact audit provenance |
| Read-only regression | committed receipt can be revalidated without triggering or mutating state |

The repository completion gate remains Ruff, Black, fast pytest, AIR3 lint,
DagBag, BDD, runtime health, Compose validation, and the focused live proof.
The known unrelated 90% coverage baseline remains report-only.
