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
requirements-pending:
  - id: R1
    reason: CI freshness steps written but never executed. Closes on the first CI run.
    owned_by: "CI execution of warehouse-dbt-contract"
  - id: R2
    reason: Same — the stale-batch exit-1 assertion has not run.
    owned_by: "CI execution of warehouse-dbt-contract"
  - id: R3
    reason: The one-batch fixture has never touched PostgreSQL.
    owned_by: "CI execution of warehouse-dbt-contract"
  - id: R10
    reason: dbt build has not run against a database in this phase.
    owned_by: "CI execution of warehouse-dbt-contract"
  - id: R11
    reason: Static half done; the live mutation-gate run has not happened.
    owned_by: "CI execution of warehouse-dbt-contract"
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

**A DAG was paused and restored.** `lakehouse_maintenance` is hourly and was
**unpaused**. Starting a scheduler would have fired it, and it writes
`marts.maintenance_runs` to the canonical `dwh` — a mutation the authorisation
excluded. It was paused before Airflow started and restored to its original
`is_paused=false` after Airflow stopped. The full paused-state snapshot was
recorded before and matched exactly after. This is an Airflow-metadata change,
not a warehouse change, and it *prevented* an unauthorised trigger.

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

Incidentally this validated the fixtures' guard by accident:
`marts.pipeline_runs` holds 8 rows, so both mutating fixtures would have refused
to run against this database. The guard works.

## What remains unproven

Every runtime freshness behaviour. `dbt source freshness` has still never
executed anywhere — not fresh, not stale. R1, R2, R3, R10 and R11 close on the
first CI run of `warehouse-dbt-contract`, not before. The thresholds remain
provisional and unmeasured by explicit decision.

## Commits

- `3a5af42` — test(03-04): prove the freshness gate against a live DagBag and the real callables

## Interface

Phase 3 delivers the gate, its configuration, its CI proof and its runtime
topology proof. The remaining evidence is CI's to produce.
