---
phase: 03-staging-source-freshness-gate
plan: 01
subsystem: database
tags: [postgres, migration, dbt, freshness, staging, airflow]

requires:
  - phase: 02-warehouse-asset-orchestrated-batch-split
    provides: the Asset-triggered marts DAG whose consumption boundary the gate will sit at
provides:
  - A batch-load transaction timestamp (`loaded_at`) on all four `stg.*` tables
  - Replay of migration 008 onto existing volumes via `scripts/bootstrap_stack.py`
  - Fast-suite contract pinning the migration, the replay, and the untouched ingestion path
affects: [03-02 source freshness config, 03-03 CI proof, 03-04 live phase gate]

tech-stack:
  added: []
  patterns:
    - "Additive idempotent db/init migration replayed through bootstrap_stack.py"

key-files:
  created:
    - db/init/008_stg_loaded_at.sql
  modified:
    - scripts/bootstrap_stack.py
    - tests/test_h1_runtime.py

key-decisions:
  - "Second module constant rather than a WAREHOUSE_MIGRATIONS tuple — the anti-overengineering ladder favours the literal precedent at two migrations; revisit at three."
  - "Migration contract test lives in tests/test_h1_runtime.py, not test_warehouse_dbt.py as the design named — the repository precedent for this exact claim about these exact two files is directly above it."
  - "The false-fresh window is accepted, not fixed. No nullable transitional column, no sentinel timestamp."
  - "now(), never clock_timestamp() — transaction-start time is what makes one batch yield one timestamp across all four tables."

patterns-established:
  - "Migration header records the invariant and the accepted trade-off, so a later reader need not rediscover why clock_timestamp is wrong."
  - "Comment lines stripped before any count() assertion on a SQL file, so header edits cannot invalidate the count."

requirements-completed: [R6, R6b, R3b, R8]

duration: ~12min
completed: 2026-08-17
---

# Phase 3 Plan 01: Arrival Signal Summary

**The four staging tables now carry the batch-load transaction timestamp the freshness gate will read, and an existing volume gains it through bootstrap rather than only on a fresh data directory.**

## What was built

`db/init/008_stg_loaded_at.sql` adds `loaded_at timestamptz not null default now()`
to `stg.orders`, `stg.order_items`, `stg.order_payments` and `stg.customers`,
using the `alter table if exists` / `add column if not exists` style of migration
007. No index, no view, no data statement.

The ingestion DAG required **zero changes**. `_copy_csv` builds an explicit
`COPY` column list that does not name `loaded_at`, so PostgreSQL supplies the
default. Because `load_raw_csv_to_stg` wraps the truncate and all four `COPY`
calls in one `with _connect() as conn:` block over a connection with default
`autocommit=False`, and `now()` is transaction-start time, one batch yields one
identical timestamp across all four tables — by construction, not coincidence.

`scripts/bootstrap_stack.py` gained `STG_LOADED_AT_MIGRATION` and a second
`_docker_exec` psql call after the existing provenance replay. Without this the
change would work on a fresh stack and silently do nothing on every existing
one.

`tests/test_h1_runtime.py::test_stg_loaded_at_migration_is_additive_and_bootstrapped`
pins the migration content, the replay, and the two facts that keep the
ingestion path out of scope: `loaded_at` appears nowhere in
`dags/warehouse_orders.py` and nowhere in `002_stg_tables.sql`.

## Verification performed

| Check | Result |
|---|---|
| Both migration contract verifies | pass |
| Untouched-ingestion-path check (working tree **and** index) | pass |
| Negative proof: replay constant removed | test went **red**, restored byte-identical |
| `ruff check .` | pass |
| `black --check .` | pass, 71 files unchanged |
| `pytest` full fast suite | **301 passed**, 60 deselected |
| Coverage gate `--cov=iceberg --cov-fail-under=90` | pass, **93.66%** |

## Not verified

Nothing in this plan required a live stack, and none was started. The migration
has **not** been applied to any running database — neither the canonical `dwh`
nor any test warehouse. Its behaviour against a real PostgreSQL instance,
including the double-application no-op (R6b), remains proven only by
`ci-h1-clean.yml`'s existing bootstrap path, which was not run here.

## Commits

- `83fb738` — feat(03-01): add the staging batch-load transaction timestamp
- `795becc` — test(03-01): pin the loaded_at migration, its replay, and the untouched load

## Interface for downstream plans

03-02 can now declare `loaded_at_field: loaded_at` on the four `staging`
sources. The column exists in `db/init` and is replayed onto existing volumes;
no further schema work is needed.
