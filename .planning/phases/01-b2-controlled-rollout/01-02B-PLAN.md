---
phase: 01-b2-controlled-rollout
plan: 02B
type: execute
wave: 4
depends_on: [01-02A]
files_modified:
  - artifacts/b2-rollout/02b-kafka-offset-baseline.json
  - artifacts/b2-rollout/02b-kafka-reconciliation.json
  - artifacts/b2-rollout/02b-checkpoint-recovery.log
  - docs/runtime/H1-reproducible-runtime.md
autonomous: true
requirements: [CAN-01]
must_haves:
  truths:
    - "The original Spark checkpoints are preserved and KAFKA_FAIL_ON_DATA_LOSS remains true."
    - "Kafka topic identity, partition bounds, checkpoint offsets, Bronze coverage, and business payload continuity are captured before any new boundary is created."
    - "A fresh streaming boundary is created only after all required historical observations are proven durable in Bronze or a bounded recovery has durably written the missing observations."
  artifacts:
    - path: "artifacts/b2-rollout/02b-kafka-offset-baseline.json"
      provides: "Topic identity, partition bounds, four checkpoint states, and Bronze continuity evidence"
      contains: "old_checkpoint_preserved, fail_on_data_loss"
    - path: "artifacts/b2-rollout/02b-kafka-reconciliation.json"
      provides: "Fail-closed offset-loss disposition and new epoch evidence"
      contains: "disposition, completeness_proven"
  key_links:
    - from: "spark/jobs/orders_streaming.py"
      to: "Kafka"
      via: "failOnDataLoss configuration"
      pattern: "failOnDataLoss"
    - from: "spark/jobs/orders_streaming.py"
      to: "MinIO/Postgres checkpoints"
      via: "four independent Structured Streaming queries"
      pattern: "RAW_CHECKPOINT_PATH|POSTGRES_CHECKPOINT_PATH|DEAD_LETTER_CHECKPOINT_PATH|RECONCILIATION_CHECKPOINT_PATH"
---

<objective>
Reconcile the Kafka checkpoint offset-loss event without confusing transport offsets with business state.

Purpose: establish a proven continuity boundary for the restored streaming query. The old checkpoint is evidence and rollback material, not something to delete or silently bypass.
</objective>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/01-b2-controlled-rollout/CONTEXT.md
@spark/jobs/orders_streaming.py
@docker-compose.extended.yml
@docs/remediation/R1-retention-and-malformed-events.md
@docs/remediation/S1.1-historical-business-version-migration.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Freeze producer/stream and capture offset continuity evidence</name>
  <files>artifacts/b2-rollout/02b-kafka-offset-baseline.json</files>
  <action>Stop orders-producer and orders-streaming only after confirming the current runtime is legacy/legacy/0; preserve all four existing checkpoint prefixes. Capture Kafka topic identity/cluster metadata, partition count, earliest/latest offsets, the failed checkpoint offsets (including 218961 versus 157), and authoritative Bronze/Silver row counts, order_id/business_version hashes, and Kafka metadata coverage. Include raw, PostgreSQL, dead-letter, and reconciliation checkpoint locations. Do not use kafka_offset as a global business identity and do not delete checkpoints, recreate the topic, truncate Kafka, or disable fail-on-data-loss.</action>
  <verify><automated>docker inspect de-demo-orders-streaming --format '{{range .Config.Env}}{{println .}}{{end}}'; docker exec de-demo-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders; docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml ps orders-producer orders-streaming; python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-kafka-offset-baseline.json')); assert p['old_checkpoint_preserved'] is True; assert p['fail_on_data_loss'] is True; assert len(p['checkpoint_paths'])==4; print('offset baseline PASS')"</automated></verify>
  <done>The old checkpoint and topic state are preserved and the exact continuity gap is quantified.</done>
</task>

<task type="auto">
  <name>Task 2: Prove completeness and establish a new checkpoint epoch</name>
  <files>artifacts/b2-rollout/02b-kafka-reconciliation.json, artifacts/b2-rollout/02b-checkpoint-recovery.log</files>
  <action>Classify the offset-loss event as complete, bounded-recoverable, or unprovable using business content (order_id, business_version, canonical payload/hash) and authoritative Bronze evidence. If all unavailable history is already durable, or a bounded replay can write the missing records idempotently and verify Bronze continuity, create a new explicitly named checkpoint epoch while retaining the old checkpoint unchanged. Restart the stream with KAFKA_FAIL_ON_DATA_LOSS=true and prove it advances from the new boundary. If completeness cannot be proven, stop with disposition=STOP and do not reset checkpoints. Never use rm, recursive deletion, startingOffsets=latest as a silent workaround, or a changed failOnDataLoss value.</action>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-kafka-reconciliation.json')); assert p['disposition'] in {'COMPLETE','BOUNDED_RECOVERY','STOP'}; assert p['fail_on_data_loss'] is True; assert p['old_checkpoint_preserved'] is True; assert not p.get('destructive_actions',[]); print('offset reconciliation receipt PASS')"; docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml logs --no-color --since 10m orders-streaming</automated></verify>
  <done>A new streaming epoch is active only with proven continuity; otherwise the phase remains safely blocked with no checkpoint reset.</done>
</task>

</tasks>

<success_criteria>
02B is green only when the Kafka offset-loss boundary is reconciled from durable business evidence, fail-on-data-loss remains enabled, old checkpoints remain preserved, and the stream starts from a documented new epoch. An unprovable gap is an explicit STOP, not a green recovery.
</success_criteria>

<output>Create .planning/phases/01-b2-controlled-rollout/01-02B-SUMMARY.md when done.</output>
