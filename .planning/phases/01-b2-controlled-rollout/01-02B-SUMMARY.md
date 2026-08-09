---
phase: 01-b2-controlled-rollout
plan: 02B
status: stop
completed: false
---

# 01-02B — Kafka checkpoint offset-loss reconciliation

## Result

`01-02B` is **STOP and fail-closed**, not green. The user manually quiesced the
producer and stream, and the Kafka range was stable on two observations. The
read-only payload reconciliation completed, but it proved that the complete
current Kafka range is missing from Bronze and that checkpoint/output epochs are
inconsistent.

## Evidence captured

- The four checkpoint prefixes were read without mutation.
- Their current terminal source offset is `157`.
- The frozen phase context records the prior failed checkpoint as `218961` versus
  available offset `157`.
- Direct Kafka Fetch decoded one partition, offsets `0..40208` continuously
  (`40209` messages); the latest exclusive offset was stable at `40209` twice.
- Bronze and Silver each contain `218961` rows with `218961` distinct
  `order_id` values and zero NULL `business_version` values.
- Bronze and Silver have the same order/version digest:
  `235686e5906e72d284f30513b8165f31ec4385f167c5d713c635e9ba225277d3`.
- All `40209` current Kafka observations are absent from Bronze; no overlapping
  payload mismatch was found.
- Historical committed landing output ends at `kafka_offset=218960`.

## Safety disposition

No recovery was attempted. No checkpoint, topic, data file, Iceberg table,
progress state, or catalog state was deleted or reset. `KAFKA_FAIL_ON_DATA_LOSS`
remains configured as `true`. No new checkpoint epoch is justified: continuing
from terminal checkpoint `157` could skip missing offsets `0..156`, while reset
to `0` and `startingOffsets=latest` are both forbidden.

Artifacts:

- `artifacts/b2-rollout/02b-kafka-offset-baseline.json`
- `artifacts/b2-rollout/02b-kafka-reconciliation.json`
- `artifacts/b2-rollout/02b-checkpoint-recovery.log`

## Resume command

Resolve the checkpoint/output epoch conflict and run the normal durable Spark
recovery path with Docker control-plane access. Do not reset the old checkpoint
or use `startingOffsets=latest`. Do not execute 01-02C or 01-03 until 01-02B is
green.
