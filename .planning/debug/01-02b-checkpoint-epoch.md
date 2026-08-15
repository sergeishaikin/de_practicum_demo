---
status: resolved
trigger: "Phase 01 / plan 01-02B is STOP because of an unresolved checkpoint/output epoch conflict. Diagnose read-only."
created: 2026-08-09
updated: 2026-08-09
goal: find_root_cause_only
diagnose_only: true
---

# Debug Session: 01-02B checkpoint/output epoch conflict

## Symptoms

- Expected: establish whether Kafka, Spark checkpoint, Landing, and Bronze
  continuity can be proven without changing runtime state.
- Actual: 01-02B is STOP and fail-closed; no continuity has been proven.
- Known evidence: the prior checkpoint boundary was 218961 while currently
  available Kafka history ends at offset 157; stable Kafka payload range was
  observed as 0..40208; Landing output ends at 218960; current checkpoint
  objects end at 157; the range is absent from Bronze.
- Constraints: preserve all existing Spark checkpoints and Docker volumes;
  do not publish Kafka records, mutate Iceberg/MinIO/PostgreSQL, reset
  checkpoints, change `startingOffsets`, or execute recovery.

## Current Focus

- hypothesis: Kafka log state was recreated/reset while persistent Landing,
  Bronze, and Spark checkpoint state survived, so the current topic offsets
  belong to a different Kafka epoch than the historical checkpoint/output
- test: inspect Compose persistence and Spark source/checkpoint configuration;
  compare their state-ownership boundaries with the observed offset ranges
- expecting: no Kafka data volume plus persistent S3A checkpoints and outputs,
  together with the 0..40208 versus 0..218960 boundaries, would support an
  epoch replacement mechanism; Docker runtime cluster identity remains unknown
- next_action: append direct code/config evidence and distinguish confirmed
  mechanism from unobserved recreation event

## Evidence

- timestamp: 2026-08-09
  observation: Session created from the explicit 01-02B diagnose-only request.

- timestamp: 2026-08-09
  checked: artifacts/b2-rollout/02b-kafka-offset-baseline.json and
    02b-kafka-reconciliation.json
  found: All four checkpoint prefixes currently terminate at source offset
    157; prior failed checkpoint evidence is 218961; stable direct Kafka fetch
    is partition 0 offsets 0..40208 (40209 continuous messages); Bronze,
    Silver, and historical Landing each contain 218961 rows with kafka_offset
    0..218960; all current Kafka observations are absent from Bronze.
  implication: transport-offset continuity between current Kafka and prior
    Landing/Bronze/checkpoint state is disproven; business completeness is not
    proven and the STOP disposition is evidence-backed.

- timestamp: 2026-08-09
  checked: docker-compose.extended.yml Kafka service and spark/jobs/orders_streaming.py
  found: Kafka service declares no volume or host data mount (lines 160-188),
    while Spark checkpoints are persistent S3A paths under
    s3a://de-practicum/checkpoints/* and outputs use persistent MinIO paths;
    Spark reads orders with startingOffsets=earliest and failOnDataLoss from
    KAFKA_FAIL_ON_DATA_LOSS (true by default).
  implication: recreating the Kafka container can reset the topic log/offset
    namespace while leaving checkpoints and Landing/Bronze intact, producing
    exactly the observed new low offsets versus old high output boundary.
    This is a confirmed architectural mechanism, but the exact Docker event
    and Kafka cluster ID are unobserved because control-plane access failed.

- timestamp: 2026-08-09
  checked: artifacts/b2-rollout/02b-kafka-offset-baseline.json
  found: docker_control_plane_available=false and cluster_id=null; no runtime
    inspect/restart or normal durable recovery was performed.
  implication: exact topic identity, cluster UUID, broker log directory
    history, and timestamp of recreation remain unknown; they cannot be
    promoted from inference to direct evidence in this session.

## Eliminated

<!-- Add eliminated hypotheses here as the diagnosis progresses. -->

## Resolution

- root_cause: Kafka topic/log state was recreated or reset into a new offset epoch while persistent Spark checkpoints and Landing/Bronze outputs from the prior epoch remained. The current 0..157 checkpoint/topic boundary cannot be reconciled with the prior 0..218960 Landing/Bronze boundary (or prior checkpoint 218961); continuity is therefore disproven. The exact recreation event and Kafka cluster UUID are unobserved.
- fix: not applied (diagnose-only; no runtime or state mutations permitted).
- verification: Read-only artifacts show current checkpoint prefixes ending at 157, direct Kafka history 0..40208, prior Landing/Bronze/Silver rows 0..218960, and no current Kafka observations represented in Bronze. Compose Kafka has no persistent volume while Spark checkpoints/outputs use persistent S3A/MinIO paths; this supports the epoch-reset mechanism. Control-plane availability was false, so topic identity and recreation timestamp remain unknown.
- files_changed: .planning/debug/01-02b-checkpoint-epoch.md (diagnostic evidence and resolution only)
