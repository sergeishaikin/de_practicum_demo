---
status: resolved
trigger: "Diagnose 01-03 STOP as a potentially stale plan-premise problem after 01-02B-NB and 01-02C."
created: 2026-08-10
updated: 2026-08-10
goal: find_root_cause_only
diagnose_only: true
---

# Debug Session: 01-03 stale manifest premise

## Symptoms

- Expected: establish whether the historical 255 LIVE_POST_MIGRATION manifests
  were already processed before 01-03, or whether they remain unproven.
- Actual: 01-03 classifier observed `classified_manifests=0` and
  `LIVE_POST_MIGRATION=0`; the plan required exactly 255.
- Related state: `work={}`, `next_sequence=258`, only 100 completed entries
  retained; Bronze/Silver totals are 218965/218964 after the bounded new-epoch
  fixture.
- Constraints: read-only diagnosis; do not drain or clean the outbox, rewrite
  progress, delete rows/manifests, mutate runtime, or execute 01-04.

## Current Focus

- hypothesis: 01-03's live-255 and absolute 218961/218961 assumptions may
  have become stale after the additive new epoch (+4 Bronze / +3 Silver); the
  current state is compatible with prior 255 processing, but exact identity
  completion remains unproven.
- test: reconcile the original 255 identity set, medallion completion/deletion
  ordering, bounded progress retention, and current baseline-relative counts.
- expecting: the current empty outbox may prove no pending work but exact
  identity completion remains unproven if pruned progress lacks an immutable
  ledger for the first 156 IDs.
- next_action: finalize one disposition from ALREADY_PROCESSED_PROVEN,
  PLAN_PREMISE_STALE, or MANIFEST_STATE_UNPROVEN using cross-artifact evidence.

## Evidence

- timestamp: 2026-08-10
  checked: artifacts/b2-rollout/01-preflight-handoff.json
  found: exactly 255 LIVE_POST_MIGRATION identities, Bronze/Silver 218961/218961.

- timestamp: 2026-08-10
  checked: artifacts/b2-rollout/02-canary-receipt.json
  found: successful B2 cycle with keys_processed=10415, work_completed=100,
  work_available=155, zero FF14 and no in-flight work.

- timestamp: 2026-08-10
  checked: artifacts/b2-rollout/03-before.json and 03-stop-receipt.json
  found: classified_manifests=0, LIVE_POST_MIGRATION=0, work/progress gates
  clear, totals 218965/218964; no identity list was created.

- timestamp: 2026-08-10
  checked: artifacts/b2-rollout/03-progress-final.json and
  iceberg/medallion/iceberg_medallion.py
  found: next_sequence=258; fixture is sequence 258; only sequences 159..257
  remain for 99 historical IDs because MAX_COMPLETED_PROGRESS=100 prunes older
  IDs; normal completion saves progress before deleting outbox.

- timestamp: 2026-08-10
  checked: historical Iceberg manifests for bronze.orders
  found: all 255 original Bronze data-file paths from the preflight handoff
  are present in historical Iceberg manifests. This is durable Bronze
  ingestion evidence, but not a per-ID B2 completion ledger: Silver snapshots
  expose no matching load-id property and retained progress entries have
  silver_snapshot_id=null.

## Resolution

- root_cause: "01-03 froze a live-outbox snapshot that no longer existed after
  earlier B2 processing, while retaining absolute historical Bronze/Silver
  counts that became stale after the additive new-epoch fixture."
- disposition: HISTORICAL_EVIDENCE_GAP
- proven: "The original 255 identities existed and were preserved at S1.2B
  preflight; all 255 Bronze data-file paths are present in historical Iceberg
  manifests; current outbox/work are empty; 99 historical IDs remain in the
  bounded progress tail; current totals reconcile as 218961+4 Bronze and
  218961+3 Silver."
- not_proven: "Per-ID B2 completion is individually durable-proven for only
  99 original IDs (progress sequences 159..257). The first 156 historical
  identities have no durable completion/deletion ledger or Silver load-id
  lineage after bounded progress pruning; Bronze file presence alone cannot
  establish that the B2 drain completed each identity."
- fix: "None in diagnose-only mode. Do not drain, clean, rewrite progress,
  delete rows/manifests, or execute 01-04."
- next_action: "Keep 01-03 STOP. Any completion requires an explicitly amended
  baseline-relative, identity-accounting proof; do not fabricate manifests or
  claim ALREADY_PROCESSED_PROVEN."
