---
phase: 01-b2-controlled-rollout
plan: 03
subsystem: controlled-rollout
tags: [b2, drain, outbox, fail-closed]
requires:
  - phase: 01-b2-controlled-rollout
    provides: 01-02C PASS guarded b2/legacy/1 canary
provides:
  - fail-closed classifier evidence for the attempted 255-manifest freeze
  - restored legacy/legacy/0 medallion runtime
affects: [01-04]
tech-stack:
  added: []
  patterns: [read-only classifier, bounded fail-closed rollback]
key-files:
  created:
    - artifacts/b2-rollout/03-before.json
    - artifacts/b2-rollout/03-progress-final.json
    - artifacts/b2-rollout/03-stop-receipt.json
  modified: []
key-decisions:
  - "Do not reinterpret an empty outbox as completion of the required 255-manifest freeze; stop before drain and preserve evidence."
  - "Restore SILVER_MODE=legacy, GOLD_SOURCE=legacy, SHADOW_COMPARE=0 after the mandatory freeze gate failed."
requirements-completed: []
duration: "~15m"
completed: 2026-08-10
status: stop
---

# Phase 1 Plan 03 Summary — STOP / freeze gate failed

The plan stopped at Task 1. The mandatory read-only classifier did not find the
required complete 255-manifest `LIVE_POST_MIGRATION` set: it observed an empty
outbox (`classified_manifests=0`, `LIVE_POST_MIGRATION=0`). Because the identity
set was not durably frozen before drain, no drain, cleanup, identity synthesis,
or dbt gate was attempted.

## Evidence

- `artifacts/b2-rollout/03-before.json` — classifier run while the active
  runtime tuple was `SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=1`.
  It reports `safe_stale=0`, `in_flight_blocked=0`, `blocked=0`, but
  `classified_manifests=0` rather than the required 255.
- `artifacts/b2-rollout/03-progress-final.json` — read-only progress capture;
  `work={}` and completed sequences extend through 258. No progress was reset,
  deleted, or rewritten.
- `artifacts/b2-rollout/03-stop-receipt.json` — post-rollback classifier
  receipt; it preserves the same empty-outbox observation and confirms
  `silver_equals_b2_projection=true`, `silver_unique_order_ids=true`, and zero
  NULL business versions.

The global counts at observation were Bronze `218965` and Silver `218964`,
which include the bounded new-epoch fixture and therefore do not satisfy the
plan's historical `218961/218961` gate. This mismatch is recorded as evidence;
no rows or tables were deleted or rewritten to force the count.

## Safety disposition

- No `cleanup_legacy_outbox.py` invocation occurred.
- No manifest identity list was fabricated; `03-live-manifests-before.txt` was
  intentionally not created because the required 255 identities were absent.
- The medallion was stopped and recreated with the rollback tuple
  `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`.
- Existing checkpoints, progress, outbox, Iceberg tables, Docker volumes, and
  new-epoch fixture rows were preserved.

## Deviations from Plan

### Fail-closed blocker

**1. Required 255-manifest freeze set unavailable**

- **Found during:** Task 1
- **Issue:** Classifier observed zero manifests, so the exact legitimate
  post-migration identity set could not be proven or compared.
- **Action:** Stopped before drain and restored legacy configuration; retained
  both classifier receipts and the progress object.

## Known Stubs

None. The plan is not marked complete because the required drain and correctness
proof were not achieved.

## Threat Flags

None. No new endpoint, auth path, file-access boundary, schema, or cleanup
operation was introduced.

## Self-Check: PASSED

- `03-before.json`, `03-progress-final.json`, and `03-stop-receipt.json` exist
  and parse as JSON.
- Runtime inspection after rollback reports
  `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`.
- No cleanup command, reset, deletion, or table rewrite was run by this plan.

---
*Phase: 01-b2-controlled-rollout*
*Plan: 03*
*Disposition: STOP (not complete)*
