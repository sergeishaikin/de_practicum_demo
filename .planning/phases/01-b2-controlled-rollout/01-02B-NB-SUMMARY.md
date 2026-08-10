---
phase: 01-b2-controlled-rollout
plan: 02B-NB
subsystem: controlled-rollout
tags: [kafka, spark, checkpoint, evidence, new-baseline]
requires: [01-02A, 01-02B, 01-02B-R]
provides: [new-baseline-ready-receipt]
affects: [01-02C]
tech-stack:
  added: []
  patterns: [fail-closed bounded rollout, immutable evidence, canonical lineage digests]
key-files:
  created:
    - artifacts/b2-rollout/02b-new-baseline-sequencing.log
    - artifacts/b2-rollout/02b-new-baseline-kafka.json
    - artifacts/b2-rollout/02b-new-baseline-counts.json
    - artifacts/b2-rollout/02b-new-baseline-readiness.json
    - artifacts/b2-rollout/02b-new-baseline-rollback.txt
  modified:
    - artifacts/b2-rollout/02b-new-baseline-volume-investigation.json
decisions:
  - "approve-new-baseline authorized one bounded epoch only; no historical replay, checkpoint reset, topic truncation, or 01-02C execution."
  - "The anonymous legacy Kafka volume was preserved while Compose created de_demo_kafka_data at /var/lib/kafka/data; broker effective log.dirs was verified before continuing."
  - "Historical continuity is not claimed; readiness is independently authorized by the new epoch receipt."
metrics:
  duration: "~35m"
  completed: "2026-08-10"
---

# Phase 01 Plan 02B-NB: New Baseline READY Summary

**Durable Kafka volume migration and a four-event canonical B2 baseline now produce matching Kafka/Landing/Bronze lineage digests with a three-row Silver deduplicated projection.**

## Accomplishments

- Stopped `orders-producer` and `orders-streaming` cleanly; all four historical checkpoint roots remained unchanged across the post-stop observation.
- Recorded prior receipt Kafka tail `40209`, preserved anonymous legacy volume `e4534efdad02ff47592f05ed7db69c1f0f961f5f8d20d66686fbdd5309696457`, and performed the one approved controlled Kafka recreation.
- Verified Docker source `de_demo_kafka_data`, target `/var/lib/kafka/data`, `KAFKA_LOG_DIRS=/var/lib/kafka/data`, and broker `log.dirs=/var/lib/kafka/data`.
- Published immutable epoch `b2-nb-20260810-01` with offsets `0..3`, four unique non-null event IDs, and canonical digest `94b574f2279b6742f62a0aa93156b8774ab33264609b49ea695047a81895e6c8`.
- Landing and Bronze each contain four matching events/digests; Silver contains three latest-version rows with digest `991d2346316848d0c5af1aff9d2405efd49cf2aaa32889d21ba3711f8c2a0fc7`.
- Fresh checkpoints exist only under `s3a://de-practicum/checkpoints/b2-new-baseline/b2-nb-20260810-01/{raw,postgres,dead-letter,reconciliation}`. Runtime was left at `legacy/legacy/0`; no 01-02C was executed.

## Evidence

- `artifacts/b2-rollout/02b-new-baseline-preflight.json`
- `artifacts/b2-rollout/02b-new-baseline-volume-investigation.json`
- `artifacts/b2-rollout/02b-new-baseline-sequencing.log`
- `artifacts/b2-rollout/02b-new-baseline-kafka.json`
- `artifacts/b2-rollout/02b-new-baseline-counts.json`
- `artifacts/b2-rollout/02b-new-baseline-readiness.json` (`disposition=READY`, `ready_for_01_02c=true`)
- `artifacts/b2-rollout/02b-new-baseline-rollback.txt`

## Deviations from Plan

### Corrected controlled volume migration

The first approved attempt stopped before recreation because it treated the absent named volume as a hard failure. After explicit re-approval, the corrected migration path preserved the anonymous volume, recreated Kafka once with Compose, and passed all post-recreation invariants before fixture publication. No historical checkpoint or topic truncation/reset was performed.

## Verification

- Focused contract suite: 34 passed (`tests/test_new_baseline_contract.py`, `tests/test_order_contract.py`, `tests/test_writer.py`).
- Readiness schema assertion: PASS (`disposition=READY`, `historical_continuity_claimed=false`, `old_checkpoints_untouched=true`, `ready_for_01_02c=true`).

## Known Stubs

None. All four layers have concrete bounded counts and canonical digests.

## Self-Check: PASSED

All required evidence files and this summary exist; historical STOP summaries and checkpoint roots remain untouched.
