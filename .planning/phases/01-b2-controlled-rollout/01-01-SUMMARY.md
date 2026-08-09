---
phase: 01-b2-controlled-rollout
plan: 01
subsystem: infra
tags: [dbt, trino, iceberg, outbox, preflight]

# Dependency graph
requires:
  - phase: S1.2B
    provides: verified legacy outbox handoff and Bronze/Silver baseline
provides:
  - durable read-only S1.2B handoff receipt
  - durable dbt parse, compile, semantic run, and test receipt
  - passed machine-readable preflight gate for the controlled B2 rollout
affects: [01-02, 01-03, 01-04, 01-05, 01-06, 01-07]

# Tech tracking
tech-stack:
  added: []
  patterns: [read-only classifier evidence, command-level dbt receipts, fail-closed rollout gate]

key-files:
  created:
    - artifacts/b2-rollout/01-preflight-runtime.txt
    - artifacts/b2-rollout/01-preflight-handoff.json
    - artifacts/b2-rollout/01-preflight-dbt.log
    - artifacts/b2-rollout/01-preflight-gate.json
    - .planning/phases/01-b2-controlled-rollout/01-01-SUMMARY.md
  modified: []

key-decisions:
  - "Keep the runtime contract at SILVER_MODE=legacy, GOLD_SOURCE=legacy, SHADOW_COMPARE=0 until Plan 02."
  - "Use the installed dbt CLI because python -m dbt is unavailable; preserve the documented dbt arguments and record the launcher deviation."
  - "Treat all 255 remaining manifests as legitimate LIVE_POST_MIGRATION work and make no data, progress, or outbox change during preflight."

patterns-established:
  - "Preflight gates assert exact handoff values before authorizing any rollout configuration change."
  - "dbt receipts record each command exit code and the final PASS/WARN/ERROR totals."

requirements-completed: [CAN-03]

# Metrics
duration: 25min
completed: 2026-08-09
---

# Phase 1 Plan 1: Preflight Baseline Summary

**Exact S1.2B handoff evidence and successful dbt semantic validation now authorize the controlled B2 rollout.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-08-09T15:04:59Z
- **Completed:** 2026-08-09T15:30:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Refreshed the read-only legacy outbox classifier receipt: `SAFE_STALE=0`, `LIVE_POST_MIGRATION=255`, `IN_FLIGHT_BLOCKED=0`, `BLOCKED=0`, and authoritative Bronze/Silver rows `218961/218961`.
- Verified Bronze and Silver have zero NULL `business_version` rows, Silver order IDs are unique, and Silver equals the accepted B2 projection.
- Ran dbt parse, compile, semantic run (`2/2 CREATE VIEW PASS`), and test (`26/26 PASS`, zero WARN/ERROR), then changed the preflight gate to `passed=true`.
- Preserved the legacy runtime contract and did not change writers, medallion services, Gold/Silver modes, progress, physical layout, or outbox data.

## Task Commits

Each task was committed atomically:

1. **Task 1: Capture the frozen legacy runtime and service boundary** - `7818ab7` (`feat`)
2. **Task 2: Prove the exact S1.2B handoff and dbt baseline** - `80fa052` (`feat`)

**Plan metadata:** Pending final metadata commit after state and roadmap updates.

## Files Created/Modified

- `artifacts/b2-rollout/01-preflight-runtime.txt` - frozen runtime/service-boundary receipt from Task 1.
- `artifacts/b2-rollout/01-preflight-handoff.json` - classifier evidence for the exact S1.2B handoff.
- `artifacts/b2-rollout/01-preflight-dbt.log` - dbt launcher, command, exit-code, and result receipt.
- `artifacts/b2-rollout/01-preflight-gate.json` - machine-readable passed gate consumed by later rollout plans.

## Decisions Made

- Retained `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, and `SHADOW_COMPARE=0`; no later-plan configuration was started.
- Used `dbt.exe` because `python -m dbt` is unavailable in this environment; the documented dbt commands and project/profile arguments were unchanged.
- Kept the 255 post-migration manifests classified as legitimate live work rather than cleanup debt.

## Deviations from Plan

### Environment-only launcher deviation

The prescribed `python -m dbt` launcher is unavailable because the installed dbt package has no `dbt.__main__`. The installed `dbt.exe` CLI was used with the same parse, compile, run, and test arguments. This is recorded in `01-preflight-dbt.log`; no dependency was installed and no gate was weakened.

### Auto-fixed Issues

**1. [Rule 1 - Receipt formatting bug] Regenerated the dbt receipt as plain text**
- **Found during:** Task 2 (dbt baseline)
- **Issue:** The first PowerShell capture encoded child-process output with NUL-separated characters, making the durable log unsuitable for machine assertions.
- **Fix:** Re-ran the same installed dbt CLI commands with a plain-text receipt and asserted all four exit codes plus the semantic and test summaries.
- **Files modified:** `artifacts/b2-rollout/01-preflight-dbt.log`
- **Verification:** `dbt` exit codes `0/0/0/0`, semantic `PASS=2`, and test `PASS=26 WARN=0 ERROR=0`.
- **Committed in:** `80fa052` (Task 2 commit)

---

**Total deviations:** 1 environment-only launcher deviation; 1 auto-fixed receipt-format issue.
**Impact on plan:** No scope expansion. The resulting evidence is stronger and all planned gates pass.

## Issues Encountered

- The prior catalog commit-uncertainty blocker was resolved before this continuation by the user’s controlled runtime quiesce and restart; the semantic dbt run then passed.
- The first commit attempt could not create `.git/index.lock` under the shell’s default permissions. The requested Task 2 commit succeeded with elevated Git metadata access and contains only the three Task 2 receipts.
- The verification suite emitted one pre-existing pytest cache permission warning; all 17 tests passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 02 may begin from the passed `artifacts/b2-rollout/01-preflight-gate.json`. The runtime remains legacy/legacy/0, and no B2 configuration change was made by this plan.

## Known Stubs

None found in the plan artifacts.

## Threat Surface Review

No new trust-boundary surface was introduced. The plan only refreshed read-only catalog evidence, ran the documented dbt semantic validation, and updated the local preflight receipts.

## Self-Check: PASSED

- `artifacts/b2-rollout/01-preflight-runtime.txt` exists.
- `artifacts/b2-rollout/01-preflight-handoff.json` exists.
- `artifacts/b2-rollout/01-preflight-dbt.log` exists.
- `artifacts/b2-rollout/01-preflight-gate.json` exists and records `passed=true`.
- Commits `7818ab7` and `80fa052` exist.

---
*Phase: 01-b2-controlled-rollout*
*Completed: 2026-08-09*
