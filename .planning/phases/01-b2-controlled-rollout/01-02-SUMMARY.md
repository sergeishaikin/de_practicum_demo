---
phase: 01-b2-controlled-rollout
plan: 02
subsystem: infra
tags: [b2, canary, iceberg, medallion, shadow-compare, rollback]

# Dependency graph
requires:
  - phase: 01-b2-controlled-rollout
    provides: passed preflight gate and verified Bronze/Silver handoff
provides:
  - guarded B2 canary runtime evidence
  - focused canary regression and live metrics evidence
  - fail-closed legacy rollback receipt after a recovery anomaly
affects: [01-03, 01-04, 01-05, 01-06, 01-07]

# Tech tracking
tech-stack:
  added: []
  patterns: [exact runtime tuple assertion, objective metrics gate, configuration-only rollback]

key-files:
  created:
    - artifacts/b2-rollout/02-canary-runtime.txt
    - artifacts/b2-rollout/02-canary-tests.log
    - artifacts/b2-rollout/02-canary-receipt.json
    - artifacts/b2-rollout/02-canary-rollback.txt
    - .planning/phases/01-b2-controlled-rollout/01-02-SUMMARY.md
  modified: []

key-decisions:
  - "Apply only SILVER_MODE=b2, GOLD_SOURCE=legacy, SHADOW_COMPARE=1 during the canary; Gold was never switched to persisted Silver."
  - "Treat the UncheckedSQLException recovery anomaly and zero successful shadow cycles as a failed canary and restore legacy/legacy/0 immediately."
  - "Do not mark CAN-01 complete because the required successful shadow cycle was not evidenced."

patterns-established:
  - "Canary evidence must include the exact container tuple, focused tests, latest metrics, and post-rollback configuration."
  - "Rollback changes only medallion environment selection and never resets data, progress, or completed outbox state."

requirements-completed: []

# Metrics
duration: 10min
completed: 2026-08-09
---

# Phase 1 Plan 2: Controlled B2 Canary Summary

**B2/legacy/shadow canary evidence captured, then safely rolled back to legacy/legacy/0 after a live recovery anomaly with no data or progress reset.**

## Performance

- **Duration:** approximately 10 min
- **Started:** 2026-08-09T15:42:58Z
- **Completed:** 2026-08-09T15:52:00Z
- **Tasks:** 2
- **Files modified:** 4 artifacts

## Accomplishments

- Applied and verified the requested live tuple `SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=1`; `validate_runtime_config` classified it as `shadow`, and Gold remained on the legacy projection.
- Ran the prescribed focused regression suite twice: `53 passed`, with only a pre-existing pytest cache permission warning.
- Queried the prescribed latest 20 medallion metrics rows. The latest row had `work_in_flight=0`, `ff14_conflicts=0`, and `shadow_mismatches=0`, but `shadow_comparisons=0`; no successful shadow cycle was evidenced.
- Detected `Medallion error: UncheckedSQLException: Unknown failure`, stopped the B2 canary, and restored `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`.
- Verified the restored container tuple and legacy rollout classification; no data, Iceberg table, progress state, or completed outbox manifest was deleted or reset.

## Task Commits

Each task was committed atomically:

1. **Task 1: Apply and verify the guarded B2 canary configuration** - `d1c2bff` (`feat`)
2. **Task 2: Run the canary safety checks and capture fail-closed behavior** - `a258350` (`feat`)
3. **Task 2 evidence completeness correction** - `900ee8d` (`fix`)

**Plan metadata:** pending final metadata commit after state and roadmap updates.

## Files Created/Modified

- `artifacts/b2-rollout/02-canary-runtime.txt` - redacted container environment, Compose validation, service status, and shadow rollout proof.
- `artifacts/b2-rollout/02-canary-tests.log` - prescribed focused pytest command and result.
- `artifacts/b2-rollout/02-canary-receipt.json` - canary result, full latest-20 metrics result, failure diagnosis, and rollback linkage.
- `artifacts/b2-rollout/02-canary-rollback.txt` - restore command, redacted post-restore environment, and no-reset assertion.

## Decisions Made

- Kept Gold on legacy throughout; no persisted-Silver Gold cutover was attempted.
- A recovery anomaly is a fail-closed canary failure even when focused unit/regression tests pass.
- CAN-01 remains pending because the live canary did not produce a successful shadow comparison cycle.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Security] Redacted credentials from the runtime evidence before commit**

- **Found during:** Task 1 commit
- **Issue:** The raw `docker inspect` environment included live AWS and database credential values; persisting them in a committed artifact would expose secrets.
- **Fix:** Replaced secret values with `<redacted>` while retaining the complete relevant runtime configuration and required canary tuple.
- **Files modified:** `artifacts/b2-rollout/02-canary-runtime.txt`, `artifacts/b2-rollout/02-canary-rollback.txt`
- **Verification:** Secret-value scan passed; required tuple and restored legacy tuple remained present.
- **Committed in:** `d1c2bff`, `a258350`

**Total deviations:** 1 auto-fixed (Rule 2).
**Impact on plan:** Security-preserving evidence redaction only; no production code, Compose YAML, data, or progress semantics changed.

## Issues Encountered

- Docker Engine named-pipe access and Git metadata writes required elevated permission in this environment; the exact authorized commands succeeded after escalation.
- The live B2 service emitted `UncheckedSQLException: Unknown failure` and did not produce a successful shadow cycle. Fail-closed rollback completed successfully.
- The pytest run emitted one pre-existing cache permission warning; all 53 focused tests passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 01-03 and all later plans were not executed. The stack is safely restored to `legacy/legacy/0`, but the rollout is blocked: investigate the `UncheckedSQLException`, then rerun Plan 01-02 before draining manifests or starting any later plan. CAN-01 remains pending.

## Known Stubs

None found in the plan artifacts.

## Threat Surface Review

No new network endpoint, authentication path, file-access pattern, or schema boundary was introduced. Runtime evidence was redacted before commit to avoid expanding the credential exposure surface.

## Self-Check: PASSED

- All four required Plan 01-02 artifacts exist.
- `02-canary-receipt.json` parses and contains all 20 queried metrics rows.
- Focused regression verification passed: 53 tests.
- Post-rollback runtime verification passed: legacy/legacy/0.
- Commits `d1c2bff`, `a258350`, and `900ee8d` exist.

---
*Phase: 01-b2-controlled-rollout*
*Completed: 2026-08-09*
