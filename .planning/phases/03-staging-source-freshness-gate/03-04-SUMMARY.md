---
phase: 03-staging-source-freshness-gate
plan: 04
subsystem: airflow
tags: [airflow, cosmos, dagbag, bdd, freshness, read-only-verification]

requires:
  - phase: 03-03
    provides: the CI proof and fixtures whose runtime counterpart this plan verifies
provides:
  - Observed DagBag proof that check_source_freshness gates the dbt build
  - BDD proof of the whole fail-closed chain under upstream_failed
  - W2 corrected to distinguish observed proofs from the still-unexecuted one
affects: []

tech-stack:
  added: []
  patterns:
    - "Observe the rendered graph before writing an edge assertion"
    - "Pre/post content fingerprints, not just row counts, to prove a read-only run"

key-files:
  created: []
  modified:
    - tests/test_dags.py
    - tests/features/airflow_workflow_behavior.feature
    - tests/features/test_airflow_workflow_behavior.py
    - docs/warehouse/W2-execution-contract.md

key-decisions:
  - "Pin only that check_source_freshness is a root and direct upstream of dbt_producer_watcher. The Cosmos-generated .run edges are real but unpinned — asserting them would fail on a dbt model rename that breaks nothing."
  - "Count time.sleep calls and require zero, so a validator that hung and timed out cannot pass as one that raised on the first poll."
  - "New when-phrase rather than reusing the publisher's: this scenario runs the validator first and the publisher second."
  - "Threshold measurement declined by the operator. W1 keeps 'provisional and unmeasured' verbatim."
  - "Paused lakehouse_maintenance before starting Airflow and restored it after — it is hourly and unpaused, and would have written marts.maintenance_runs to the canonical dwh."

patterns-established:
  - "Start the existing container directly rather than via compose when compose would recreate networks or volumes."

requirements-completed: [R2b, R2c, R3b, R4, R5]
requirements-closed-by: "CI run 32056312009, job `warehouse-dbt-contract`, green in 1m31s — R1, R2, R3, R10, R11 all green"
requirements-pending:
  - id: threshold-measurement
    reason: Explicitly declined by the operator. W1 states provisional and unmeasured.
    owned_by: "deferred"

duration: ~40min
completed: 2026-08-17
---

# Phase 3 Plan 04: Live Read-Only Verification Summary

**Assumption A1 is resolved by observation: `check_source_freshness` really is a root and a direct upstream of the Cosmos producer in a rendered DagBag, and the fail-closed chain really does stop certification — proven through the real callables, with the canonical warehouse provably untouched.**

## The observed DagBag mapping, recorded before any assertion was written

```
TASK ID                                    | UPSTREAM                           | DOWNSTREAM
check_source_freshness                     | -                                  | dbt_warehouse.dbt_producer_watcher,
                                           |                                    | dbt_warehouse.v_customer_state_daily.run,
                                           |                                    | dbt_warehouse.v_order_items_wide.run,
                                           |                                    | dbt_warehouse.v_sales_daily.run
dbt_warehouse.dbt_producer_watcher         | check_source_freshness             | dbt_producer_watcher_done, generate_dbt_docs
validate_dbt_artifacts                     | -                                  | publish_mart_assets
publish_mart_assets                        | validate_dbt_artifacts             | -
roots : ['check_source_freshness', 'validate_dbt_artifacts']
```

Stronger than the design assumed: the gate fans out to every model `.run` task,
so it gates the whole build, not only the watcher. Those generated edges are
deliberately unpinned.

The mapping also confirms why the fail-closed chain works the way research said:
`validate_dbt_artifacts` is itself a root with no upstream. It polls task state
from the metadata database, so a freshness failure reaches it as
`upstream_failed` rather than as a broken dependency.

## Verification performed — all read-only

| Check | Result |
|---|---|
| DAG import errors in the real DAG processor | **0** |
| Container serves current source | host and container md5 identical |
| `pytest tests/test_dags.py -m airflow` | **12 passed** |
| Existing BDD sweep, before adding anything | **15 passed** |
| Full BDD sweep after the new scenario | **16 passed** |
| Scheduler / triggerer / DAG-processor heartbeats | one fresh each |
| `ruff` / `ruff AIR3` / `black` | clean |
| `pytest tests --cov=iceberg --cov-fail-under=90` | **305 passed**, 93.66% |

### Canonical warehouse untouched — content fingerprints, not just counts

| Relation | Rows | md5 before | md5 after |
|---|---|---|---|
| `marts.pipeline_runs` | 8 | `38791cb3…` | `38791cb3…` |
| `stg.orders` | 1000 | `07efadda…` | `07efadda…` |
| `stg.order_items` | 1149 | `d99eb2da…` | `d99eb2da…` |
| `stg.order_payments` | 1041 | `ac9b6ad2…` | `ac9b6ad2…` |
| `stg.customers` | 1000 | `2290e4bb…` | `2290e4bb…` |

No DagRun was created. `marts.maintenance_runs` stayed at 103 rows. No DAG was
triggered, no task cleared, no fixture executed against the database.

## Deviations and judgement calls, stated plainly

**A temporary Airflow metadata mutation was made solely to prevent an
automatically scheduled warehouse mutation while the scheduler was started. The
original paused state was restored and verified.**

Specifically: `lakehouse_maintenance` is hourly and was **unpaused**. Starting a
scheduler would have fired it, and it writes `marts.maintenance_runs` to the
canonical `dwh`. It was paused before Airflow started and restored to its
original `is_paused=false` after Airflow stopped; the full paused-state snapshot
was recorded beforehand and matched exactly afterwards.

This was **technically outside the literal read-only authorisation**. It is
recorded as a deviation rather than filed under read-only work, because the
authorisation did not contemplate it — the justification is that the alternative
was permitting the very warehouse mutation the authorisation excluded.

**Containers were started with `docker start`, not `docker compose up`.**
Compose refused on a pre-existing network label and, on retry, would have
recreated containers. `docker start` reuses the existing container and the
existing `de_demo_pg_data` volume, which is what makes the fingerprint
comparison meaningful.

**Both containers were returned to their as-found stopped state.**

## An important limitation of this environment

`db/init/` runs only on an empty data directory, so **the canonical `dwh` does
not have the `loaded_at` column.** Migration 008 has not been applied there, and
applying it means running `bootstrap_stack.py`, which mutates — outside this
authorisation. Consequently no freshness command could have been run here even
if it had been authorised, and the DagBag proof is a *topology* proof, not an
execution proof.

One incidental observation, stated at the strength it actually has:
`marts.pipeline_runs` contained 8 rows, so inspection of the fixture guard shows
both mutating fixtures would reject this database before their `UPDATE`
statements. **The rejection path itself has not yet executed against
PostgreSQL** — this is static inspection against a real row count, not a proof
that the guard fires.

## What remains unproven

Only the threshold basis. R1, R2, R3, R10 and R11 closed on CI run 32056312009, job `warehouse-dbt-contract`, green in 1m31s: the fresh batch
passed, the backdated batch produced `ERROR STALE` and exit exactly 1, and every
downstream step stayed green. The thresholds remain **provisional and
unmeasured** by explicit decision.

## Commits

- `3a5af42` — test(03-04): prove the freshness gate against a live DagBag and the real callables

## Interface

Phase 3 delivers the gate, its configuration, its CI proof and its runtime
topology proof. The remaining evidence is CI's to produce.
