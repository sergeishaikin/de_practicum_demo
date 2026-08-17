---
phase: 03-staging-source-freshness-gate
plan: 03
subsystem: testing
tags: [ci, github-actions, dbt, freshness, postgres, fixtures]

requires:
  - phase: 03-02
    provides: the freshness config and the check_source_freshness gate the CI steps exercise
provides:
  - Three staging load-timestamp SQL fixtures, guarded and deterministic
  - Four CI steps proving fresh-pass and stale-fail-closed on the pinned runtime
  - Contract tests pinning fixture safety and CI step order
affects: [03-04 live DagBag and BDD proof]

tech-stack:
  added: []
  patterns:
    - "Determinism by writing the timestamp, never by waiting for it"
    - "Exit-code assertions strict on the exact code, not merely non-zero"

key-files:
  created:
    - tests/fixtures/warehouse/assert_loaded_at_is_one_batch.sql
    - tests/fixtures/warehouse/backdate_staging_loaded_at.sql
    - tests/fixtures/warehouse/reset_staging_loaded_at.sql
  modified:
    - .github/workflows/ci-pr.yml
    - tests/test_warehouse_dbt.py

key-decisions:
  - "The stale step requires exit code exactly 1. Any non-zero would also accept exit 2 — a dbt crash — letting a broken command masquerade as a working gate."
  - "Status captured with `|| status=$?`, which records the code rather than discarding it. Not the swallowing idiom, which the contract test forbids."
  - "The swallow prohibition is scoped to the four new steps: the job's own Cleanup step legitimately swallows, so a job-wide form could only be made green by weakening the gate."
  - "A dedicated one-batch fixture rather than appending to assert_marts.sql, so it can run immediately after the seed and before any backdating — which is what proves the load's own transaction."
  - "All four tables backdated, not just stg.orders, so no reader concludes the other three are exempt."

patterns-established:
  - "Comment-stripped bodies before any count() or forbidden-substring assertion, so prose cannot fail a behavioural check."
  - "Step lookup by ASCII substring; em-dash mismatches must not surface as a bare ValueError."

requirements-completed: [R1, R1c, R2, R3, R8]
requirements-pending:
  - id: R10
    reason: >-
      Inherited from 03-02. `dbt build` is present in the job but has not been
      executed here — no stack was started. Closes when CI runs the job.
    owned_by: "CI execution of warehouse-dbt-contract"
  - id: R11
    reason: >-
      The static half is done — `dbt source freshness` is asserted absent from
      scripts/mutation_test.py. The live half, that the mutation gate still
      passes with the new steps present, closes when CI runs the job.
    owned_by: "CI execution of warehouse-dbt-contract"

duration: ~30min
completed: 2026-08-17
---

# Phase 3 Plan 03: CI Proof Summary

**The executable proof is written: a freshly seeded batch must pass freshness, a batch backdated past `error_after` must exit exactly 1, and staging is unconditionally restored afterwards.**

Written, not yet run. These steps have never executed — that happens when CI
runs the job.

## What was built

Three fixtures under `tests/fixtures/warehouse/`.
`assert_loaded_at_is_one_batch.sql` is non-mutating and fails in both
directions: more than one distinct `loaded_at` means the load was not one
transaction, zero means staging is empty. Both mutating fixtures carry the same
`marts.pipeline_runs` emptiness guard `seed_staging.sql` uses, and the reset
wraps its four updates in one transaction because that is what restores the
one-batch-one-timestamp invariant.

Four CI steps, inserted between the seed and the dbt build, touching no existing
step (44 insertions, 0 deletions).

## Verification performed

| Check | Result |
|---|---|
| `pytest tests/test_warehouse_dbt.py` | 15 passed |
| Negative proof: guard removed from backdate fixture | **red**, right message, restored |
| Negative proof: `if: always()` removed from reset | **red**, restored |
| Negative proof: backdate/reset swapped | **red** with observed indices, restored |
| `ci-pr.yml` parses as YAML | pass |
| Existing steps unmodified | 44 insertions, **0 deletions** |
| sqlfluff scope unchanged | pass |
| `ruff` / `black` | clean |
| `pytest tests --cov=iceberg --cov-fail-under=90` | **305 passed**, 93.66% |

## Not verified

**Nothing in this plan has been executed against a database.** No stack was
started. `dbt source freshness` has never run — not on a fresh batch, not on a
stale one. The three fixtures have never touched PostgreSQL, so their SQL is
syntactically unverified beyond mirroring existing fixtures. R10 and R11's live
halves remain open and close only when CI runs the job.

## A recurring friction worth recording

Three times now a strict substring guard has been tripped by *prose explaining
the guard* — `warn_error` in a DAG comment, the promise sentence wrapped across
lines in W1, and the swallowing idiom named inside a CI step's own comment. Each
time the fix was to reword the prose, never to weaken the guard. The pattern to
carry forward: inside any region a contract test scans by substring, do not
write the forbidden token even to explain it. Name it in the documentation
instead.

## Commits

- `d80b23f` — test(03-03): add the staging load-timestamp fixtures and pin their safety
- `eeebac9` — test(03-03): prove the freshness gate on the pinned runtime in CI

## Interface for downstream plans

`03-04` still owns everything runtime: the observed DagBag mapping, the BDD
fail-closed scenario, and the threshold measurement decision.
