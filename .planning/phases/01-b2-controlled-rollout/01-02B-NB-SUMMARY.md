---
phase: 01-b2-controlled-rollout
plan: 02B-NB
subsystem: controlled-rollout
tags: [kafka, spark, checkpoint, evidence, stop]
requires: [01-02A, 01-02B, 01-02B-R]
provides: [new-baseline-stop-receipt]
affects: [01-02C]
tech-stack:
  added: []
  patterns: [fail-closed bounded rollout, immutable evidence]
key-files:
  created:
    - artifacts/b2-rollout/02b-new-baseline-sequencing.log
    - artifacts/b2-rollout/02b-new-baseline-kafka.json
    - artifacts/b2-rollout/02b-new-baseline-counts.json
    - artifacts/b2-rollout/02b-new-baseline-readiness.json
    - artifacts/b2-rollout/02b-new-baseline-rollback.txt
  modified: []
decisions:
  - "approve-new-baseline was honored only until the required named Kafka volume precondition failed; disposition is STOP."
  - "Historical continuity is not claimed and 01-02C is not authorized."
metrics:
  duration: "~15m"
  completed: "2026-08-10"
---

# Phase 01 Plan 02B-NB: New Baseline STOP Summary

Task 3 executed after the explicit `approve-new-baseline` decision. The two
streaming services were stopped cleanly, all four historical checkpoint roots
were observed unchanged across a five-second interval, and the Kafka tail was
recorded as partition 0 latest-exclusive offset 40209. The stateful start then
failed closed because the running broker was attached to an anonymous volume;
the required named `de_demo_kafka_data` volume did not exist. No Kafka restart,
volume creation/reset, fixture publication, Spark start, checkpoint mutation,
topic recreation, or truncation was attempted.

The runtime tuple remains `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`,
`SHADOW_COMPARE=0`. `historical_continuity_claimed=false`,
`old_checkpoints_untouched=true`, and `ready_for_01_02C=false`.

## Evidence

- `artifacts/b2-rollout/02b-new-baseline-sequencing.log`
- `artifacts/b2-rollout/02b-new-baseline-kafka.json`
- `artifacts/b2-rollout/02b-new-baseline-counts.json`
- `artifacts/b2-rollout/02b-new-baseline-readiness.json`
- `artifacts/b2-rollout/02b-new-baseline-rollback.txt`

## Deviations from Plan

### Auto-stopped precondition failure (fail closed)

The required durable Kafka volume could not be verified: `de-demo-kafka` was
mounted on anonymous volume `e4534efdad02ff47592f05ed7db69c1f0f961f5f8d20d66686fbdd5309696457`
and `de_demo_kafka_data` was absent. Per the plan, execution stopped without a
destructive retry and emitted STOP/rollback evidence.

## Known Stubs

Layer fixture counts and canonical digests are intentionally null because no
new epoch was started after the durable-volume precondition failed. This STOP
receipt must not be treated as authorization for 01-02C.

## Verification

- Focused contract suite: 34 passed (`tests/test_new_baseline_contract.py`, `tests/test_order_contract.py`, `tests/test_writer.py`).
- Readiness schema assertion: PASS (`disposition=STOP`, `ready_for_01_02C=false`).
