---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 02
subsystem: observability
tags: [postgres, metrics, prometheus, schema, migration, iceberg]

requires:
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 01
    provides: inserted_row() name-keyed insert assertions, which verify this plan's schema change
provides:
  - Seven additive columns on marts.lakehouse_metrics (cycle_id, phase, three snapshot ids, two skip booleans)
  - PHASES closed set and keyword-only Metrics.record parameters
  - Cycle-only Prometheus observation, closing the gauge-reset defect
  - classify_metric_row(), the status-qualified historical interpretation rule as executable code
affects: [04-03 cycle identity, 04-05 Gold skip, 04-06 shadow certificate, 04-07 documentation contract]

tech-stack:
  added: []
  patterns:
    - "Additive schema extension in both the create-table body and as alter-table-add-column-if-not-exists lines, per the M5 precedent"

key-files:
  created: []
  modified:
    - iceberg/common/ops.py
    - tests/test_ops.py

key-decisions:
  - "cycle_id, phase and the three snapshot ids are nullable with no default, and that is load-bearing: `cycle_id is null` is the predicate separating pre-Phase-4 rows from Phase-4 rows. A `not null default ''` would destroy it."
  - "Historical rows are never backfilled with cycle_id, for the same reason — an un-instrumented run must not be able to masquerade as an instrumented one."
  - "No new status literal. 'The fast path was taken' is expressed by the boolean columns: postgres_exporter.py hard-codes the status set for SOURCE_UP and alerts.yml keys LakehouseApplicationFailure on status='failed'; a new literal would silently break both."
  - "self.runtime.observe runs only when phase is None or 'cycle'. None keeps the writer's behaviour byte-for-byte — the writer passes no phase and must be untouched by this phase."
  - "No phase label, no new collector, no new metric name. Per-phase granularity lives in PostgreSQL only, so every Grafana target and alert expression keeps working unchanged."
  - "classify_metric_row returns 'nested' — not 'b2' — for status='failed'. A failed row is emitted either by run_b2 or by _legacy_silver_cycle under QUALITY_FAIL_ON_VIOLATIONS=1, and the function cannot tell which. Returning 'b2' would assert an origin the evidence does not support, in the one requirement whose whole point is evidential honesty. 'nested' is deliberately not a member of PHASES."
  - "One 04-01 assertion was narrowed: 'every other column is 0' was written when every other column was numeric, and the identity columns are legitimately null/false. Scoped to counters, with the identity columns covered by their own test rather than dropped."

patterns-established:
  - "A non-obvious guard carries a comment stating why, so a later reader is not tempted to remove it."

requirements-completed: [MTL-01, MTL-02, REGR-4]

duration: unrecorded (reconstructed post-hoc)
completed: 2026-08-18
---

# Phase 4 Plan 02: Metric Identity in the Sink Summary

**`marts.lakehouse_metrics` can now say which cycle a row belongs to and which phase of that cycle it describes; the Prometheus gauge-reset defect is closed; and the historical interpretation rule is executable code rather than prose.**

> **Reconstructed summary.** This file was written after the fact from the plan,
> commit `0151005`, and a re-run of the verification gate. It was not produced by
> the executor at execution time.

## What was built

**Schema (Task 1).** Seven additive columns — `cycle_id text`, `phase text`,
`bronze_snapshot_id bigint`, `silver_snapshot_id bigint`, `gold_snapshot_id bigint`,
`shadow_skipped boolean not null default false`, `gold_skipped boolean not null
default false` — in both the `create table if not exists` body (fresh databases)
and as `alter table ... add column if not exists` lines (existing volumes),
exactly as the seventeen M5 columns already are. `Metrics.record` gained matching
defaulted keyword-only parameters, and `PHASES = ("b2", "shadow", "gold", "cycle")`
documents the closed set. No existing caller changed.

**Prometheus (Task 2).** `_RuntimeMetrics` labels every gauge by `source` alone,
so the outer medallion record was overwriting the nested B2 gauges *with zeros*:
`lakehouse_files{kind="planned"}`, `lakehouse_bytes`,
`lakehouse_processed{kind="keys"}` and `lakehouse_work{state="in_flight"}` reset
seconds after being measured, directly weakening the `LakehouseUnresolvedWork`
alert. The `self.runtime.observe(...)` call is now guarded on
`phase in (None, "cycle")` ([ops.py:221](iceberg/common/ops.py#L221)), with a
comment recording why. One logical cycle now produces one Prometheus event, one
duration observation, and one set of gauge values.

**The historical rule (Task 3).** `classify_metric_row()` is a pure function with
no I/O and no new imports. For Phase-4-era rows (`cycle_id` not None) it returns
the row's own `phase` verbatim. For pre-Phase-4 rows it applies the locked
four-branch table from `04-CONTEXT.md`, including the safety-critical
`status="shadow_failed"` branch that the naive duration-only rule misclassifies.

## Verification performed

| Check | Result |
|---|---|
| `pytest -q --cov=iceberg --cov-fail-under=90` | **319 passed**, 61 deselected |
| Coverage gate | pass, **93.72%** (`iceberg/common/ops.py` at **100%**) |
| `ruff check .` | All checks passed |
| `black --check .` | pass, 71 files unchanged |
| `git diff observability/` | **empty** — byte-identical |
| `test_runtime_metric_contract_is_exposed_by_application_paths` | still green |

Re-run independently at HEAD `0151005` during summary reconstruction; all figures
above are from that re-run, not quoted from the commit message.

## Deviation from the plan

The plan structured this work as three TDD tasks and therefore anticipated three
commits. All three tasks landed in a **single commit** (`0151005`), whose message
narrates Task 1's rationale in detail and covers Tasks 2 and 3 only implicitly.
All three tasks' acceptance criteria were checked directly against the code during
reconstruction and are satisfied: `PHASES` at
[ops.py:91](iceberg/common/ops.py#L91), `classify_metric_row` at
[ops.py:94](iceberg/common/ops.py#L94), the guard at
[ops.py:221](iceberg/common/ops.py#L221).

## Not verified

The `alter table ... add column if not exists` path has **not** been applied to
any running database — neither the canonical `dwh` nor any test warehouse. Its
behaviour against a live PostgreSQL instance, including the double-application
no-op, is proven only by the auto-DDL path's existing structure and by unit tests
against a fake cursor. No live stack was started.

The gauge-reset fix is likewise proven by unit assertions on the collector
registry, not by observing a real Prometheus scrape.

## Commits

- `0151005` — feat(04-02): give lakehouse_metrics a cycle and phase identity

## Interface for downstream plans

04-03 can call `Metrics.record(..., cycle_id=..., phase=...)` and rely on nested
phase records reaching PostgreSQL without touching a Prometheus collector. The
exporter's `distinct on (source)` consumer is unchanged in meaning, so 04-03 must
keep the `cycle` record last. 04-05 and 04-06 have `gold_skipped` /
`shadow_skipped` and the three snapshot-id columns available. 04-07 must document
the deliberate Prometheus per-phase exclusion.
