---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 01
subsystem: testing
tags: [test-infrastructure, metrics, fakes, clock, iceberg, gold]

requires:
  - phase: 03-staging-source-freshness-gate
    provides: the completed prior phase; this plan has no code dependency on it
provides:
  - FakeMetrics.phase(name) / FakeMetrics.cycle() uniqueness-asserting accessors
  - scripted_monotonic for exact-integer duration assertions
  - inserted_row() name-keyed insert-parameter assertions with a column/parameter length check
  - A snapshot-aware local Gold/Silver double recording snapshot_properties and current_snapshot()
affects: [04-02 sink schema, 04-03 cycle identity, 04-05 Gold provenance]

tech-stack:
  added: []
  patterns:
    - "Test doubles assert uniqueness rather than returning first/last, so a duplicate-emission defect fails instead of hiding"
    - "Insert assertions parse the column list out of the SQL and zip it with the parameter tuple"

key-files:
  created: []
  modified:
    - tests/support/fakes.py
    - tests/test_ops.py
    - tests/test_m4_gold.py

key-decisions:
  - "phase(name)/cycle() assert uniqueness instead of returning the first or last match — a run emitting two records for one phase is a defect in the thing under test, and picking one would conceal it."
  - "scripted_monotonic raises when run past the end of its script rather than repeating the last value — overrunning means the code under test called the clock more times than anticipated, which is worth failing on."
  - "The length check in inserted_row is the load-bearing part: it proves the statement's column list and its parameter tuple still agree, which is exactly the failure a column added without a matching parameter would cause."
  - "The local Gold FakeTable stays duplicated rather than converging on tests/support/fakes.py — the shared double's scan() yields None for an empty table, while several Gold tests depend on an empty typed Arrow table. Converging them would change empty-scan semantics for every other consumer."
  - "The run_b2 stub takes keyword arguments. This corrects 04-RESEARCH.md §5c, which claimed a bare *args lambda absorbs an added keyword-only argument — it does not, it raises TypeError, and 04-03 will call run_b2(..., cycle_id=...)."

patterns-established:
  - "Land test infrastructure as its own wave, before the change it verifies, so later assertions are written before the change rather than adjusted after it."

requirements-completed: [MTL-01, MTL-02, GLD-01, REGR-1, REGR-2, REGR-3, REGR-4]

duration: unrecorded (reconstructed post-hoc)
completed: 2026-08-18
---

# Phase 4 Plan 01: Wave 0 Test Infrastructure Summary

**Four test-infrastructure gaps that every later Phase 4 plan depends on are closed, with no production code change at all.**

> **Reconstructed summary.** This file was written after the fact from the plan,
> the three commits, and a re-run of the verification gate. It was not produced
> by the executor at execution time.

## What was built

`records[-1]` stops naming anything in particular once one logical medallion run
emits several records — which is precisely what plan 04-03 introduces.
`tests/support/fakes.py` gains `FakeMetrics.phase(name)` and `FakeMetrics.cycle()`,
which select by phase and assert uniqueness, plus `scripted_monotonic` so phase
durations are asserted as exact integers instead of whatever the machine happened
to do. `record()` and `records` are unchanged, so every existing `records[-1]`
call site keeps working.

`tests/test_ops.py` gains `inserted_row()`. The positional form it replaces was
length-sensitive and index-shifting: adding one column to the statement silently
moved every later value, so a test could keep passing while asserting the wrong
thing. `inserted_row` reads the column list out of the statement itself and zips
it with the parameters. This landed as a standalone commit before any DDL change,
so 04-02's schema work is verified by assertions written before it.

`tests/test_m4_gold.py`'s local `FakeTable` had no `current_snapshot()` and
discarded `snapshot_properties`, so it could not express Gold provenance at all.
It now records what each write carried and which snapshot is current, mirroring
`tests/support/fakes.py` field-for-field.

## Verification performed

| Check | Result |
|---|---|
| `inserted_row` length check fires | verified — a 3-parameter tuple against a 2-column list raises |
| `iceberg/common/ops.py` unmodified by the `inserted_row` commit | byte-identical |
| Gold double self-proof, incl. the fixture 04-05 needs | pass — a bare newer snapshot hides an older property-bearing one |
| `pytest -q tests/test_ops.py tests/test_observability.py tests/test_m4_gold.py` | 49 passed (re-run at HEAD `0151005`) |

The Gold double's own tests encode why the newer-snapshot rule matters: a Trino
maintenance rewrite can drop the provenance property, and trusting the older
property-bearing snapshot would certify Gold against a Silver snapshot that no
longer produced it.

## Not verified

No production code was touched, so nothing here was exercised against a live
stack, a real PostgreSQL instance, or a real Iceberg table. These are test
doubles; their fidelity to the real `Metrics` sink and to PyIceberg's snapshot
semantics is asserted by construction, not measured.

## Commits

- `0d34d22` — test(04-01): let a metrics double name the record it means
- `c9581e6` — test(04-01): key insert assertions by column name, not position
- `1f34231` — test(04-01): make the Gold double snapshot-aware

## Interface for downstream plans

04-02 can extend the insert statement's column list without adjusting positional
slices. 04-03 can assert exact per-phase durations via `scripted_monotonic` and
name records via `FakeMetrics.phase(...)`, and may call `run_b2(..., cycle_id=...)`.
04-05 has the snapshot-provenance fixture it needs.

The fifth Wave 0 gap named in `04-VALIDATION.md` — the medallion harness liveness
signal — is deliberately **not** here. It must ship with GLD-01 and is handled in
plan 04-04.
