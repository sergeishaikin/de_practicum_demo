---
phase: 01-b2-controlled-rollout
plan: 02C
subsystem: controlled-rollout
tags: [b2, medallion, shadow-compare, postgres-catalog, kafka, canary]
requires:
  - phase: 01-b2-controlled-rollout
    provides: catalog concurrency recovery and PostgreSQL backend (01-02A)
  - phase: 01-b2-controlled-rollout
    provides: bounded new-epoch baseline b2-nb-20260810-01 (01-02B-NB)
provides:
  - fresh B2 non-empty shadow-success evidence with legacy Gold retained
  - focused regression suite evidence and fail-closed rollback boundary
affects: [01-03]
tech-stack:
  added: []
  patterns: [guarded b2/legacy/1 canary, fresh shadow evidence, immutable rollback boundary]
key-files:
  created:
    - artifacts/b2-rollout/02c-canary-runtime.txt
    - artifacts/b2-rollout/02c-canary-tests.log
    - artifacts/b2-rollout/02c-canary-receipt.json
    - artifacts/b2-rollout/02c-canary-rollback.txt
  modified: []
key-decisions:
  - "Authorized the guarded tuple SILVER_MODE=b2, GOLD_SOURCE=legacy, SHADOW_COMPARE=1 only after both green receipts and legacy/legacy/0 precondition."
  - "Accepted only a fresh non-empty B2 work metric paired with shadow_comparisons=1, zero mismatches/FF14/inflight, and preserved new-epoch evidence."
  - "Kept persisted-Silver Gold cutover and 01-03 out of scope; rollback target remains legacy/legacy/0."
patterns-established:
  - "Every canary receipt records fixture epoch, pre/post progress, backend, tuple, and fresh metric timestamps."
requirements-completed: [CAN-01]
duration: "~30m"
completed: 2026-08-10
---

# Phase 1 Plan 02C Summary

**Fresh B2 canary passed with a non-empty work cycle and zero-mismatch shadow comparison while Gold stayed on the legacy projection.**

## Performance

- **Duration:** ~30m
- **Started:** 2026-08-10T12:10:00Z
- **Completed:** 2026-08-10T12:40:46Z
- **Tasks:** 2
- **Files modified:** 4 evidence artifacts (ignored runtime artifacts; summary is tracked)

## Accomplishments

- Verified `02a-catalog-recovery.json` (`passed=true`) and `02b-new-baseline-readiness.json` (`READY`, `ready_for_01_02C=true`) before changing the runtime.
- Applied and inspected the exact `b2/legacy/1` tuple with `KAFKA_FAIL_ON_DATA_LOSS=true`; PostgreSQL remains the Iceberg catalog backend and persisted-Silver Gold stayed disabled.
- Observed fresh B2 work (`keys_processed=3`) followed by fresh shadow success (`shadow_comparisons=1`, `shadow_mismatches=0`, `ff14_conflicts=0`, `work_in_flight=0`). Fixture scope remained 4 Bronze rows and 3 latest Silver rows for `b2-nb-20260810-01`.
- Ran the exact focused suite: **78 passed, 1 deselected**.

## Task Commits

Evidence artifacts are intentionally ignored by the repository (`artifacts/`). The summary and state metadata are committed by the parent executor's final metadata commit.

## Files Created/Modified

- `artifacts/b2-rollout/02c-canary-runtime.txt` - tuple, health, backend, epoch, progress, and fresh metric capture.
- `artifacts/b2-rollout/02c-canary-tests.log` - exact focused pytest command and result.
- `artifacts/b2-rollout/02c-canary-receipt.json` - machine-readable PASS receipt with fresh shadow evidence.
- `artifacts/b2-rollout/02c-canary-rollback.txt` - immutable legacy/legacy/0 fail-closed boundary.

## Decisions Made

- Proceeding from the new baseline is authorized only for this bounded canary; no historical continuity claim or checkpoint reset was made.
- Fresh non-empty B2 work plus a subsequent shadow-success row is required; historical legacy-only success rows are not used as canary proof.

## Deviations from Plan

None - plan executed as written. A transient PostgreSQL administrator-termination error appeared while Compose recycled the dependent database during medallion recreation; the catalog recovered, and subsequent fresh B2/shadow cycles were successful. No lock, data-loss, progress, or correctness failure occurred.

## Issues Encountered

- Compose dependency startup briefly interrupted an Iceberg REST JDBC connection. Health recovered without resetting any volume, checkpoint, progress, outbox, or table; the runtime evidence records the event and the successful post-stability cycles.

## Known Stubs

None. All required canary evidence and rollback artifacts contain concrete values.

## Threat Flags

None. No new endpoint, auth path, file-access boundary, or schema surface was introduced.

## Next Phase Readiness

01-02C is PASS and provides the only authorization for the next drain/cutover plan. Keep Gold on legacy until 01-03 explicitly applies its own approval and shadow gates; preserve old checkpoints and the `b2-nb-20260810-01` epoch.

## Self-Check: PASSED

- All four 02C evidence files exist and `02c-canary-receipt.json` parses as valid JSON.
- Receipt asserts `successful_shadow_cycle=true`, `shadow_comparisons=1`, `shadow_mismatches=0`, `ff14_conflicts=0`, and `unresolved_progress=0`.
- Focused suite result is recorded as 78 passed / 1 deselected.

---
*Phase: 01-b2-controlled-rollout*
*Completed: 2026-08-10*
