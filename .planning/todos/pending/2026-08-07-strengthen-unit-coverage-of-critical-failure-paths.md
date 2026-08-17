---
created: 2026-08-07T18:08:39.341Z
updated: 2026-08-17
title: Strengthen unit coverage of critical failure paths
area: testing
priority: low (the 90% gate now passes with margin)
files:
  - tests/test_medallion.py
  - tests/test_writer.py
---

## Problem

The premise recorded on 2026-08-07 (90% overall; ops 96%, medallion 90%, writer
88%) went stale when the O1 Prometheus runtime, the S1 business-version
migration and the S1.2 outbox reconciliation landed on 8–9 August without
dependency-free unit coverage. That dropped total `iceberg/` coverage to 79.80%
and turned the CI gate into a known failure.

Coverage remediation has since run as its own task: `_RuntimeMetrics`,
`migrate()`, `reconcile_inflight_noop()` and `build_live_receipt()` are now
covered, and the gate passes at **93.40%** (289 fast tests). `ops.py` is at
100%, the two `legacy_*` utilities at 98–99%.

What remains is the original point, which was never about the percentage: some
real failure paths in the steady-state writer and medallion are still untested.
`iceberg_writer.py` sits at 91% and `iceberg_medallion.py` at 90%.

## Solution

Only if the added coverage targets real branches, not filler:

- Quality failures: invalid `status`, negative amount, future timestamp,
  duplicate `kafka_offset`.
- Retry exhaustion: `MAX_APPEND_ATTEMPTS` reached → commit re-raised → error
  path cleans pending (partially covered; add an explicit
  exhaustion-on-last-attempt assert).
- Maintenance helpers: SQL generation for `expire_snapshots`, `optimize`,
  `remove_orphan_files` and orphan cleanup logic (extract to a pure helper if
  needed).

Keep the suite fast and dependency-free. Do not chase the `sys.path` bootstrap
lines or `if __name__ == "__main__"` guards that make up most of the remaining
misses in the `legacy_*` modules.

## Notes

Two findings from the coverage work are already resolved and are not part of
this todo: `legacy_outbox_reconciliation._payload_key` was dead code and has
been deleted (the identically named helper in
`legacy_business_version_migration.py` is live and stays), and
`build_live_receipt()` now reports B2 projection validity instead of raising out
of the projection step — see `docs/remediation/S1.2-legacy-outbox-handoff.md`.
