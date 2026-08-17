---
phase: 03-staging-source-freshness-gate
plan: 02
subsystem: airflow
tags: [dbt, cosmos, airflow, freshness, postgres, docs]

requires:
  - phase: 03-01
    provides: the loaded_at batch-load transaction timestamp on the four stg.* tables
provides:
  - Freshness declared on exactly the four staging sources, none on core.*
  - A distinct check_source_freshness task wired upstream of the Cosmos dbt build
  - W1/W2 describing the implemented state, with thresholds labelled provisional and unmeasured
affects: [03-03 CI executable proof, 03-04 live DagBag and BDD proof]

tech-stack:
  added: []
  patterns:
    - "Gate at the point of consumption, not immediately after the load"
    - "Scope-guard tests that forbid gate-weakening parameters by plain substring"

key-files:
  created: []
  modified:
    - dbt/warehouse/models/sources.yml
    - dags/warehouse_dbt.py
    - docs/warehouse/W1-dbt-ownership.md
    - docs/warehouse/W2-execution-contract.md
    - tests/test_warehouse_dbt.py

key-decisions:
  - "Separate import line for DbtSourceLocalOperator — it is not re-exported from cosmos.operators in 1.15.0, and merging it takes down the whole DagBag."
  - "core.* declares nothing at all. dbt does not select a source without thresholds, so freshness: {} would be unnecessary and misleading."
  - "The dbt flag that promotes warn into error is named in W1, not in the DAG comment, so the test scope guard can forbid it by plain substring."
  - "W2 records the gate as configured but NOT yet exercised — the CI proof is 03-03's and the rendered producer edge is 03-04's."
  - "Threshold metric named as ingestion DagRun end → check_source_freshness TaskInstance start; pipeline_runs.run_ts and the 40/45-minute timeouts explicitly ruled out as the basis."

patterns-established:
  - "Manifest assertions key by (source_name, table) — orders and order_items exist under both staging and core, so bare-name comparison gives false positives."
  - "Exact-set assertions over count assertions where a later addition could slip through."

requirements-completed: [R2d, R7, R9, R10]

duration: ~25min
completed: 2026-08-17
---

# Phase 3 Plan 02: Gate Activation Summary

**The freshness gate is implemented and configured: the four staging sources declare load recency, `check_source_freshness` is wired upstream of the dbt build, and the documentation describes the implemented state.**

Deliberately *not* claimed: the gate is not yet proven at runtime. Stale/fresh
execution proof is `03-03`. The rendered Airflow edge and fail-closed
orchestration proof is `03-04`.

## What was built

`sources.yml` declares `loaded_at_field: loaded_at` with `warn_after` and
`error_after` under `config:` on `orders`, `order_items`, `order_payments` and
`customers`. `core.*` declares nothing — it is a derived, transactionally
rebuilt projection rather than an arrival point, and dbt simply does not select
a source without thresholds.

`dags/warehouse_dbt.py` gained a `DbtSourceLocalOperator` named
`check_source_freshness`, wired `check_source_freshness >> dbt_group`. The
import is on its own line for a reason recorded in a code comment.

W1's "Not adopted, deliberately" paragraph is gone, replaced by a **Load
recency** layer covering the mechanism, arrival-versus-business time, the
batch-load-transaction-timestamp naming, the rejected alternatives, the promise
verbatim with its explicit denial of missing-batch detection, what it does
catch, the accepted false-fresh window, result-status-not-exit-code, the two
adjacent behaviours, the threshold basis, and the operational consequence.

W2 gained a layer row marked **configured; not yet exercised** and a section
tracing the designed fail-closed chain while stating plainly which two proofs
are outstanding.

## Verification performed

| Check | Result |
|---|---|
| `dbt parse` on pinned dbt-core 1.12.2 | exits 0 |
| Manifest: freshness on exactly the staging set | pass, keyed by `(source, table)` |
| `core.*` freshness / `loaded_at_field` | none |
| `loaded_at_query` anywhere | absent |
| DAG wiring + 4 forbidden params absent | pass |
| Docs describe implemented state | pass |
| `docs/TESTING.md` unmodified | confirmed via `git diff --name-only` |
| `ruff check .` / `ruff check dags --select AIR3 --preview` / `black` | clean |
| Negative proof: freshness under `core` | first test **red**, restored |
| Negative proof: merged cosmos import | second test **red**, restored |
| `pytest tests --cov=iceberg --cov-fail-under=90` | **303 passed**, 93.66% |

## Not verified

**The DAG was never imported.** Airflow and Cosmos are not installed on the
host, so `DbtSourceLocalOperator`'s constructor signature, the rendered task
set, and the existence of the real producer edge are all unproven here.
`check_source_freshness >> dbt_group` is source-text wiring.

**No dbt command touched a database.** `dbt parse` does not connect. No
freshness run, fresh or stale, has been executed anywhere. No stack was started;
the canonical `dwh` was not read or written.

## Two defects found and fixed during execution

- The DAG comment originally contained the literal `warn_error`, which trips the
  scope guard forbidding that token. Reworded the comment rather than weakening
  the guard, and moved the flag's name into W1 where documentation belongs.
- W1's promise sentence was line-wrapped, so the verbatim substring assertion
  could not match. Promoted it to an unwrapped blockquote — better style for a
  quoted promise anyway.

One false alarm worth recording: the first manifest check compared source names
bare and reported `core declares freshness: ['order_items', 'orders']`. Those
table names exist under *both* source names; the check was wrong, not the
config. Assertions now key by `(source_name, name)`.

## Commits

- `05a94f7` — feat(03-02): gate mart certification on staging load recency
- `7578a6e` — test(03-02): pin the freshness source set and the gate wiring

## Interface for downstream plans

`03-03` can add the CI fresh-pass / stale-fail steps; the config they exercise
is in place. `03-04` must observe a live DagBag before asserting the producer
edge — nothing here proves it.
