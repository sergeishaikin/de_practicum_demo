---
phase: 01-b2-controlled-rollout
plan: 03F
type: execute
wave: 9
depends_on: [01-03]
files_modified:
  - iceberg/medallion/iceberg_medallion.py
  - tests/test_b2_medallion.py
  - artifacts/b2-rollout/03f-forward-ledger-receipt.json
autonomous: true
requirements: [CAN-03]
must_haves:
  truths:
    - "01-03 remains STOP / HISTORICAL_EVIDENCE_GAP and no historical identity is backfilled."
    - "Every future successful B2 manifest leaves immutable per-identity durable completion evidence independent of bounded progress retention."
    - "Failed or in-flight work cannot create a successful completion receipt."
  artifacts:
    - path: "iceberg/medallion/iceberg_medallion.py"
      provides: "Append-only per-manifest completion ledger written after Silver commit"
      contains: "completion-ledger"
    - path: "tests/test_b2_medallion.py"
      provides: "Focused ledger, retry, failure, pruning, and no-backfill tests"
      contains: "completion receipt"
    - path: "artifacts/b2-rollout/03f-forward-ledger-receipt.json"
      provides: "Bounded new-cycle proof of durable completion evidence"
      contains: "ready_for_01_04=true"
  key_links:
    - from: "iceberg/medallion/iceberg_medallion.py"
      to: "streaming/medallion/completion-ledger/<load_id>.json"
      via: "immutable receipt written only after successful Silver commit"
    - from: "streaming/medallion/completion-ledger/<load_id>.json"
      to: "bounded operational progress"
      via: "ledger remains when completed entries are pruned"

---

# 01-03F — Forward Manifest Completion Evidence

## Objective

Close the forward-only evidence gap discovered by 01-03. Preserve the
historical STOP exactly as-is; do not replay or fabricate the 156 unprovable
identities and do not modify or execute 01-04 until this plan passes.

## Tasks

### Task 1: Add the minimal immutable completion ledger

Implement a durable per-manifest receipt in the existing object-store
namespace `streaming/medallion/completion-ledger/<load_id>.json`. Record the
manifest identity, load/sequence identity, source paths and epoch when
available, completion timestamp, successful result, Silver snapshot id, and
output digest when naturally available. Write the receipt only after the
corresponding Silver commit succeeds. Preserve bounded `progress.json` as the
operational scheduler state; the ledger is audit evidence only.

### Task 2: Add focused tests

Prove successful completion appends one receipt, duplicate/retry processing is
idempotent and identity-safe, failures leave no success receipt, pruning the
bounded progress tail leaves receipts intact, and pre-existing historical
progress does not fabricate ledger entries.

### Task 3: Run one bounded new processing cycle

Use one new non-historical fixture manifest only. Do not replay the original
255 manifests. Verify the fixture reaches successful B2 completion, its
immutable receipt remains present after bounded progress trimming, and the
runtime/current data invariants remain reconciled. Produce
`03f-forward-ledger-receipt.json` with `ready_for_01_04=true` only if all
forward evidence checks pass. Do not execute 01-04.

## Success criteria

- Historical state remains `01-03 = STOP / HISTORICAL_EVIDENCE_GAP`.
- No historical completion evidence is fabricated or backfilled.
- Focused tests pass.
- One bounded new cycle has durable per-identity completion evidence that is
  independent of bounded progress retention.
- `01-04` remains unexecuted and is gated on this plan.
