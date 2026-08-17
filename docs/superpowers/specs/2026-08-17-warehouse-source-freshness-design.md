# Warehouse source freshness — design

Date: 2026-08-17
Status: approved design, not yet implemented
Scope: `dbt/warehouse`, `stg.*` schema, `warehouse_marts_validation`

## Problem

The warehouse dbt project covers unit tests, enforced contracts, data tests,
property tests, source-to-mart and staging-to-core reconciliation, replay
parity, a SQL mutation gate, and an integration fixture. One data-quality
dimension is absent: nothing asserts *when the staging data physically
arrived*. A marts run triggered hours after ingestion certifies and publishes
marts from a stale slice with every existing gate green.

`docs/warehouse/W1-dbt-ownership.md` currently records freshness as
deliberately not adopted, on the grounds that `stg.*` carries no
`loaded_at_field`. That reason is accurate but is a description of the gap
rather than a justification for it. This design closes it.

## What the warehouse offers today

Three findings constrain the design. Each was verified against the repository,
not assumed.

**`ingest_date` cannot serve as the signal.** It is not merely date-only — it
is a CSV column. `data/raw/olist_orders_dataset.csv` carries `ingest_date` in
its header, and `_copy_csv` in `dags/warehouse_orders.py` names it in the
explicit `COPY` column list. Its value is whatever the input file says, and
carries no relationship to arrival time.

**No existing audit table can back a `loaded_at_query`.** The only
arrival-shaped timestamp in the schema is
`marts.pipeline_runs.run_ts timestamptz not null default now()`
(`db/init/004_smoke_objects.sql`). That row is written by
`dags/warehouse_dbt.py`, the *marts* DAG, after `dbt build` completes; the
ingestion DAG inserts nothing into it. Using it to gate `dbt build` would be
circular — the signal is produced after the step it is meant to guard.

**`stg.*` has no timestamp column.** `db/init/002_stg_tables.sql` defines four
tables of business columns plus `ingest_date date not null`.

The arrival signal therefore has to be created. It does not already exist in
any usable form.

## Decision

Add a physical arrival timestamp to the four staging tables, declare
`loaded_at_field` freshness on all four dbt sources, and enforce it as an
Airflow task in `warehouse_marts_validation` that runs before the Cosmos dbt
build.

### Rejected alternatives

**Audit-table-backed `loaded_at_query`.** Preferred in the abstract — it keeps
the staging schema untouched — but it requires building the audit table that
does not exist, plus a new ingestion task and four queries, to produce a signal
the defaulted column yields for free. The usual objection to a physical column
(backfilling every existing row) does not apply here: `db/pipeline_sql/00_truncate_stg.sql`
truncates all four tables before every batch, so there is nothing to backfill.

**Freshness in the ingestion DAG, before the core rebuild.** Catches staleness
earliest and would prevent a stale slice reaching `core`. Rejected because it
puts a dbt invocation inside `warehouse_orders_ingestion`, which today is pure
`COPY` plus psql, and crosses the dbt ownership boundary W1 draws at the marts
layer. It would also require the warehouse dbt runtime in the ingestion image.

**Standalone nightly or PR freshness job.** Rejected outright. Ingestion is
manual-trigger by design, so an unconditional scheduled freshness check is
permanently red, gets muted, and stops carrying signal.

## Design

### 1. Arrival signal — `db/init/008_stg_loaded_at.sql`

```sql
alter table if exists stg.orders
  add column if not exists loaded_at timestamptz not null default now();
alter table if exists stg.order_items
  add column if not exists loaded_at timestamptz not null default now();
alter table if exists stg.order_payments
  add column if not exists loaded_at timestamptz not null default now();
alter table if exists stg.customers
  add column if not exists loaded_at timestamptz not null default now();
```

Idempotent, matching the `if exists` / `if not exists` style of
`db/init/007_pipeline_runs_ingestion_provenance.sql`.

Two properties make this work without touching the ingestion DAG:

- `_copy_csv` builds an explicit column list that does not name `loaded_at`, so
  the column default applies on every `COPY`.
- `now()` in PostgreSQL is transaction-start time, and `load_raw_csv_to_stg`
  wraps the truncate and all four `COPY` calls in one `with _connect() as conn:`
  block over a `psycopg2` connection with default `autocommit=False`
  (`dags/warehouse_orders.py:254`). The whole load is therefore a single
  transaction, and every row of **all four tables** receives an identical
  `loaded_at`. This gives batch-arrival semantics rather than a per-row smear,
  and makes the four sources' freshness consistent by construction rather than
  by coincidence. `clock_timestamp()` would be wrong here.

**Migration delivery.** `db/init/` is mounted at
`/docker-entrypoint-initdb.d` (`docker-compose.yml`), which PostgreSQL runs
only on an empty data directory. Existing volumes will not pick the column up.
`scripts/bootstrap_stack.py` already establishes the precedent: it holds
`PIPELINE_PROVENANCE_MIGRATION` pointing at `007_...sql` and replays it through
`psql --set=ON_ERROR_STOP=1 --file`. The new migration must be added to that
replay path. Omitting this is the most likely way for this change to appear to
work locally and fail on an existing stack.

### 2. Source configuration — `dbt/warehouse/models/sources.yml`

Applied to all four `staging` tables:

```yaml
config:
  loaded_at_field: loaded_at
  freshness:
    warn_after:  {count: 30, period: minute}
    error_after: {count: 2,  period: hour}
```

Verified available in the pinned runtime: `SourceConfig` in
`.venv-dbt-warehouse/Lib/site-packages/dbt/artifacts/resources/v1/source_definition.py`
declares `freshness`, `loaded_at_field`, and `loaded_at_query` under dbt-core
1.12.2.

`core.*` sources receive no freshness configuration. They are a derived,
transactionally rebuilt projection, not an arrival point; their recency is a
function of the staging slice they were rebuilt from, which is what the
staging check already measures.

### 3. Gate — `dags/warehouse_dbt.py`

A `check_source_freshness` task, wired upstream of the existing task group:

```python
freshness_task >> dbt_group
```

`dbt source freshness` is a distinct command from `dbt build`; the build does
not invoke it and remains independently runnable. On an error-level result the
task fails, `dbt_group` never starts, and therefore `validate_dbt_artifacts`
never certifies and `publish_mart_assets` never emits — no mart Asset and no
`marts.pipeline_runs` row can claim success for a stale slice.

Existing constants to reuse rather than redefine: `DBT_PROJECT_PATH`,
`DBT_PROFILE_PATH`, `DBT_EXECUTABLE`, `DBT_ENV`, and `_profile_config()`.

Operator choice is deliberately left to the implementation plan's first task —
see *Must be verified before implementation* below.

### 4. Tests

Repository contracts in `tests/test_warehouse_dbt.py` (no database required,
runs in the fast suite):

- all four staging sources declare `loaded_at_field: loaded_at` and both
  thresholds;
- `core.*` sources declare no freshness;
- `dags/warehouse_dbt.py` wires the freshness task upstream of `dbt_group`;
- `scripts/bootstrap_stack.py` replays `008_stg_loaded_at.sql`.

Live behaviour in the `warehouse-dbt-contract` job of `.github/workflows/ci-pr.yml`:

- **fresh batch passes** — the job seeds staging and builds in the same run, so
  `loaded_at` is seconds old; `dbt source freshness` must exit zero;
- **stale batch errors** —
  `update stg.orders set loaded_at = now() - interval '3 hours';`
  then `dbt source freshness` must exit non-zero, after which `loaded_at` is
  reset before the remaining steps.

The stale case is deterministic because `loaded_at` is a column under test
control: no sleeping, no wall-clock coupling, no flakiness. This is what keeps
the existing fixture assertions time-independent.

Migration idempotency: applying `008` twice must be a no-op.

### 5. Documentation

- `docs/warehouse/W1-dbt-ownership.md` — replace the "Not adopted,
  deliberately: dbt source freshness" paragraph with the adopted design, the
  arrival-versus-business-time rationale, and the rejected alternatives.
- `docs/warehouse/W2-execution-contract.md` — add a freshness row to the
  "Where each layer is exercised" table.

## Acceptance criteria

| Criterion | How it is met |
|---|---|
| Freshness defined for all four staging sources | `sources.yml`, asserted by a repository contract test |
| Represents physical arrival, not business event time | `loaded_at timestamptz default now()` set at `COPY` time; `ingest_date` and `order_purchase_timestamp` explicitly not used |
| Fresh batch → PASS | CI seeds and checks in the same job; asserted by exit code |
| Deliberately stale batch → WARN/ERROR | CI backdates `loaded_at` by 3 hours, exceeding `error_after`, and asserts non-zero exit. **The `warn_after` threshold is not separately asserted**: a warn is advisory, exits zero, and gates nothing, so a test for it would assert on log text rather than behaviour. |
| Missing batch → detected | **Partly pre-existing.** The ingestion DAG already enforces exact non-empty parity across all four CSV/staging pairs before emitting core events. Freshness adds arrival *recency*, which is genuinely new; it is not net-new missing-batch detection. |
| `dbt build` remains independent | Separate command, separate task; the build never invokes freshness |
| Fixture tests do not become time-dependent | `loaded_at` is test-controlled; the stale case is an explicit `update`, not a wait |
| Airflow surfaces failure before mart certification | `freshness_task >> dbt_group`; nothing downstream runs on failure |

## Operational consequences

**A manual re-trigger of `warehouse_marts_validation` more than two hours after
ingestion will fail.** This is a real workflow change. It is arguably the
correct behaviour — marts should not be re-certified against a stale slice —
but after redeploying dbt models an operator must re-run ingestion rather than
re-triggering marts alone.

An escape hatch was discussed and is **not** part of this design: an Airflow
Param defaulting to enforced that can be disabled for a deliberate re-run. If
the workflow cost proves real in practice, that is the change to make, as its
own scoped task.

## Non-goals

- No freshness on `core.*`.
- No nightly or standalone freshness job.
- No change to the existing exact-parity staging gate.
- No change to `dbt build`, the mutation gate, or any existing test.
- No `loaded_at_query`, and no new audit table.

## Must be verified before implementation

These are stated as checks rather than assertions because the stack was not
running and Cosmos is not installed on the host.

1. **Exit-code semantics.** Confirm `dbt source freshness` exits non-zero on an
   error-level source and zero on `warn`/`pass` under dbt-core 1.12.2. The gate
   depends on this. If it does not hold, read `target/sources.json` and fail on
   `status == "error"` instead.
2. **Operator choice.** Confirm whether `DbtSourceLocalOperator` exists in
   astronomer-cosmos 1.15.0 and accepts the project's `ProfileConfig`. If it
   does, use it, consistent with the existing `DbtDocsOperator` usage. If not,
   use an `@task` that shells out via `subprocess.run` with `DBT_ENV`.
3. **Threshold realism.** Confirm that on a real stack the Asset-triggered
   marts run starts well inside 30 minutes of ingestion, so `warn_after` does
   not fire on healthy runs.

## Verification

Documentation and YAML changes do not require the Python completion gate. The
schema, DAG, and test changes do:

```bash
uv run --locked ruff check .
uv run --locked black --check .
uv run --locked pytest
uv run --locked ruff check dags --select AIR3 --preview
uv run --locked pytest tests/test_dags.py -m airflow
```

Live checks, which require an authorized stateful run:

```bash
.venv-dbt-warehouse/Scripts/dbt.exe source freshness \
  --project-dir dbt/warehouse --profiles-dir dbt/warehouse
```
