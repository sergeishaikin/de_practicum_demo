---
phase: 01-b2-controlled-rollout
plan: 02B-NB
type: execute
wave: 6
depends_on: [01-02A, 01-02B, 01-02B-R]
historical_predecessor_status: STOP
scope: deliberate new B2 baseline; not historical recovery
files_modified:
  - docker-compose.extended.yml
  - kafka/producer/orders_producer.py
  - spark/jobs/orders_streaming.py
  - iceberg/writer/iceberg_writer.py
  - tests/test_new_baseline_contract.py
  - artifacts/b2-rollout/02b-new-baseline-preflight.json
  - artifacts/b2-rollout/02b-new-baseline-sequencing.log
  - artifacts/b2-rollout/02b-new-baseline-kafka.json
  - artifacts/b2-rollout/02b-new-baseline-counts.json
  - artifacts/b2-rollout/02b-new-baseline-readiness.json
  - artifacts/b2-rollout/02b-new-baseline-rollback.txt
autonomous: false
requirements: [CAN-01]
must_haves:
  truths:
    - "Kafka records for the deliberate epoch survive container recreation through an explicitly mounted Docker volume and declared log directory."
    - "Every valid new-epoch event carries a non-null source_epoch_id and unique event_id, and its canonical payload/hash is preserved unchanged from producer through Spark, Landing, and Bronze."
    - "The four new Spark checkpoint roots are explicitly named for the new epoch while every historical checkpoint root remains untouched and KAFKA_FAIL_ON_DATA_LOSS remains true."
    - "Kafka, Landing, Bronze, and Silver counts plus canonical lineage digests are captured for one bounded source window with no claim of historical continuity."
    - "01-02C can start only when the new-baseline readiness receipt is READY; any failed check emits STOP and a rollback receipt instead."
  artifacts:
    - path: "artifacts/b2-rollout/02b-new-baseline-preflight.json"
      provides: "Read-only preflight of historical STOP evidence, Kafka identity/offset tail, volume configuration, and checkpoint paths"
      contains: "historical_stop_immutable, old_checkpoint_paths, source_epoch_id, approval_required"
    - path: "artifacts/b2-rollout/02b-new-baseline-kafka.json"
      provides: "Bounded new-epoch Kafka window with exact offsets, event IDs, and canonical digest"
      contains: "source_epoch_id, first_offsets, last_offsets, event_count, canonical_digest"
    - path: "artifacts/b2-rollout/02b-new-baseline-counts.json"
      provides: "Deterministic Kafka/Landing/Bronze/Silver counts and hashes"
      contains: "kafka, landing, bronze, silver"
    - path: "artifacts/b2-rollout/02b-new-baseline-readiness.json"
      provides: "Single authorization gate consumed by 01-02C"
      contains: "ready_for_01_02c, disposition, approval, rollback"
    - path: "artifacts/b2-rollout/02b-new-baseline-rollback.txt"
      provides: "Fail-closed rollback/STOP receipt that preserves old state"
      contains: "legacy/legacy/0, historical_checkpoints_untouched"
  key_links:
    - from: "kafka/producer/orders_producer.py"
      to: "spark/jobs/orders_streaming.py"
      via: "source_epoch_id, event_id, canonical_payload, canonical_payload_hash fields and hash verification"
      pattern: "source_epoch_id|event_id|canonical_payload_hash"
    - from: "spark/jobs/orders_streaming.py"
      to: "iceberg/writer/iceberg_writer.py"
      via: "Landing Parquet columns preserved into Bronze TABLE_SCHEMA"
      pattern: "canonical_payload_hash"
    - from: "artifacts/b2-rollout/02b-new-baseline-readiness.json"
      to: "01-02C"
      via: "sole readiness prerequisite; no historical 02B continuity claim"
      pattern: "ready_for_01_02c"
---

<objective>
Establish a deliberate, independently identified B2 baseline after historical
`01-02B` and `01-02B-R` both stopped. Make the Kafka log durable, carry
explicit epoch/event and canonical payload lineage into Bronze, run one bounded
new epoch on fresh named Spark checkpoints, and publish deterministic layer
receipts. This plan is not a replay, repair, or continuity claim for the
historical Kafka range.

Purpose: give `01-02C` one reviewable, fail-closed authorization artifact while
preserving all historical checkpoints, summaries, data, and STOP dispositions.
Output: new-baseline runtime contracts, focused tests, namespaced evidence, and
`02b-new-baseline-readiness.json` as the only prerequisite for `01-02C`.
</objective>

<execution_context>
@C:/Users/serge/.codex/get-shit-done/workflows/execute-plan.md
@C:/Users/serge/.codex/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/01-b2-controlled-rollout/CONTEXT.md
@.planning/phases/01-b2-controlled-rollout/01-02B-SUMMARY.md
@.planning/phases/01-b2-controlled-rollout/01-02B-R-SUMMARY.md
@docker-compose.extended.yml
@kafka/producer/orders_producer.py
@spark/jobs/orders_streaming.py
@iceberg/writer/iceberg_writer.py
@tests/test_order_contract.py
@tests/test_writer.py

Historical `01-02B-PLAN.md`, `01-02B-SUMMARY.md`, `01-02B-R-PLAN.md`, and
`01-02B-R-SUMMARY.md` are immutable evidence. Do not edit them, rebuild their
Kafka range, create a recovery verification plan, or modify `01-02C` in this
plan. Do not introduce a generic event framework, schema registry, new
orchestration engine, Silver/Gold redesign, or unrelated cleanup.
</context>

<source_audit>

| Source | Item | Coverage |
|---|---|---|
| GOAL | Drain B2 safely with evidence-based gates after the historical recovery STOP | Covered by the bounded new epoch, receipts, and sole readiness gate |
| REQ | CAN-01 (`SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=1` remains a later canary concern) | Covered as the new-baseline authorization input to 01-02C; this plan does not switch Gold |
| RESEARCH | No phase `RESEARCH.md` exists; no additional research-scoped feature is present | No unplanned research items |
| CONTEXT | Preserve checkpoints, keep fail-on-data-loss true, stop on unproven identity/completeness, and keep Gold legacy until canary evidence | Covered by preflight, explicit epoch paths, rollback/STOP, and readiness fields |
| CONTEXT | Deferred D-3a/O2, multi-writer, and residual cleanup remain out of scope | Explicitly excluded |

</source_audit>

<tasks>

<task type="auto">
  <name>Task 1: Add durable new-baseline persistence and lineage contracts</name>
  <files>docker-compose.extended.yml, kafka/producer/orders_producer.py, spark/jobs/orders_streaming.py, iceberg/writer/iceberg_writer.py, tests/test_new_baseline_contract.py, artifacts/b2-rollout/02b-new-baseline-preflight.json</files>
  <action>Make only the contract/config changes needed for a deliberate new epoch. In `docker-compose.extended.yml`, mount a named `de_demo_kafka_data` volume at the Kafka image's explicit log directory (declare the matching `KAFKA_LOG_DIRS` value) and expose explicit new-baseline epoch/checkpoint overrides without changing the historical checkpoint defaults. In the producer, accept an explicit `SOURCE_EPOCH_ID`, create a unique `event_id`, and define canonical payload bytes as compact UTF-8 JSON with sorted keys over only the domain fields (`order_id`, `customer`, `amount`, `country`, `status`, `business_version`, `event_time`); emit that canonical payload and its SHA-256 `canonical_payload_hash` in every event. In Spark, extend the existing order schema and sink dataframes to carry `source_epoch_id`, `event_id`, `canonical_payload`, and `canonical_payload_hash`, recompute and reject a mismatched hash or wrong configured epoch, and retain `KAFKA_FAIL_ON_DATA_LOSS=true`. In the Landing-to-Bronze writer schema, add the same lineage columns as optional additive fields and preserve their values; do not change Silver/Gold schemas or deduplication authority. Add focused offline tests that assert canonicalization/hash stability, required/non-null epoch and event identity, duplicate event-id rejection, Spark/Parquet/Bronze field declarations, and the named Kafka volume plus untouched historical checkpoint defaults. Before any service start, write a read-only preflight receipt under the new-baseline namespace containing the historical STOP digests/status, current topic/partition tail, four old checkpoint paths, the configured Kafka volume/log path, the proposed epoch ID, proposed four new checkpoint paths, and `approval_required=true`.</action>
  <verify>
    <automated>python -m pytest -q tests/test_new_baseline_contract.py tests/test_order_contract.py tests/test_writer.py; docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config --quiet; python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-new-baseline-preflight.json')); assert p['historical_stop_immutable'] is True and p['approval_required'] is True; assert len(p['old_checkpoint_paths']) == 4 and len(p['new_checkpoint_paths']) == 4; assert p['fail_on_data_loss'] is True; print('new-baseline contract/preflight PASS')"</automated>
  </verify>
  <done>The producer, Spark, Landing, and Bronze contracts carry explicit lineage and verifiable canonical hashes; Kafka persistence and fresh checkpoint overrides are declared; all focused tests pass; no stateful service or historical checkpoint has been mutated.</done>
</task>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 2: Approve exactly one stateful new-epoch start</name>
  <files>none (decision checkpoint; reads artifacts/b2-rollout/02b-new-baseline-preflight.json)</files>
  <action>Pause before any producer, Kafka, or Spark state transition. Present the preflight, focused-test result, proposed epoch identity, explicit Kafka tail, fresh checkpoint paths, and rollback target for one approve-or-stop decision. Do not start services, publish records, or mutate checkpoints while awaiting the decision.</action>
  <decision>Authorize the bounded new-baseline epoch described by the read-only preflight, or keep the phase STOP.</decision>
  <context>The preflight and focused tests must be reviewed before any producer, Kafka, or Spark state transition. Approval is limited to this new epoch and does not approve historical replay, checkpoint reset, topic truncation, `startingOffsets=latest` as a hidden recovery shortcut, or a Gold cutover.</context>
  <options>
    <option id="approve-new-baseline">
      <name>Approve new baseline</name>
      <pros>Allows Task 3 to quiesce the old stream, record an explicit tail, start the named epoch, and produce the readiness receipt.</pros>
      <cons>Creates a new bounded Kafka/checkpoint/output epoch that is intentionally independent of the historical STOP range.</cons>
    </option>
    <option id="stop-new-baseline">
      <name>Keep STOP</name>
      <pros>Leaves all services, checkpoints, topic data, and historical evidence untouched for later review.</pros>
      <cons>`ready_for_01_02C` remains false and the rollout cannot proceed.</cons>
    </option>
  </options>
  <what-built>Contract tests and a read-only `02b-new-baseline-preflight.json` naming the exact source epoch, Kafka tail, durable log mount, old checkpoint roots, new checkpoint roots, and rollback target.</what-built>
  <how-to-verify>Review the preflight JSON and test output. Confirm `historical_stop_immutable=true`, `fail_on_data_loss=true`, four old paths are listed unchanged, four new paths are distinct and namespaced by the proposed epoch, and no service start or publish has occurred.</how-to-verify>
  <resume-signal>Select `approve-new-baseline` or `stop-new-baseline`.</resume-signal>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-new-baseline-preflight.json')); assert p['historical_stop_immutable'] is True and p['approval_required'] is True and p['fail_on_data_loss'] is True; assert len(p['old_checkpoint_paths']) == len(p['new_checkpoint_paths']) == 4; print('approval preflight PASS')"</automated></verify>
  <done>Exactly one explicit approval or STOP decision is recorded; Task 3 is permitted to start stateful work only for `approve-new-baseline`.</done>
</task>

<task type="auto">
  <name>Task 3: Execute the bounded epoch and emit the sole readiness gate</name>
  <files>artifacts/b2-rollout/02b-new-baseline-sequencing.log, artifacts/b2-rollout/02b-new-baseline-kafka.json, artifacts/b2-rollout/02b-new-baseline-counts.json, artifacts/b2-rollout/02b-new-baseline-readiness.json, artifacts/b2-rollout/02b-new-baseline-rollback.txt</files>
  <action>Run only after `approve-new-baseline`. Follow this exact stateful sequence and append each transition to `02b-new-baseline-sequencing.log`: (1) stop `orders-producer` and `orders-streaming`, wait for clean exit, and prove the four historical checkpoint roots have no post-stop writes; (2) inspect the Kafka topic and record per-partition tail offsets before the new epoch; (3) start Kafka with the named `de_demo_kafka_data` volume and verify the mounted `KAFKA_LOG_DIRS` path; (4) choose one immutable `SOURCE_EPOCH_ID`, publish a fixed bounded fixture with deterministic event IDs/canonical payload hashes, and start Spark with four fresh paths under `s3a://de-practicum/checkpoints/b2-new-baseline/<SOURCE_EPOCH_ID>/{raw,postgres,dead-letter,reconciliation}` and explicit per-partition offsets equal to the recorded post-approval tail, while keeping fail-on-data-loss true; (5) stop input at the fixture boundary, wait for Landing and Bronze commits, then query Kafka, Landing Parquet, Bronze, and Silver. Write `02b-new-baseline-kafka.json` with exact source-window offsets, event count, unique event-id count, and a sorted canonical digest. Write `02b-new-baseline-counts.json` with exact counts and deterministic lineage digests for Kafka, Landing, Bronze, and the deduplicated Silver projection (Silver may derive its digest by joining selected `(order_id,business_version)` rows to Bronze; do not add a Silver schema). Require Kafka/Landing/Bronze counts and digests to agree on valid events, no null/duplicate lineage, and Silver count/hash to match the fixture's declared deduplication result. Only then write `02b-new-baseline-readiness.json` with `disposition=READY`, `approval=approve-new-baseline`, `historical_continuity_claimed=false`, `old_checkpoints_untouched=true`, all contract/count/hash/checkpoint/volume checks green, and `ready_for_01_02C=true`; this receipt is the only prerequisite for 01-02C. On any failed precondition, missing/hash-mismatched/duplicate event, offset loss, old-checkpoint mutation, volume mismatch, nondeterministic boundary, or layer digest/count mismatch, stop the new services, restore `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`, write `disposition=STOP` and `ready_for_01_02C=false` plus `02b-new-baseline-rollback.txt`, and preserve every old and new evidence object. Never delete/reset historical checkpoints, truncate/recreate the historical topic, rewrite Bronze/Silver, claim historical recovery, or proceed to 01-02C from any artifact other than a READY receipt.</action>
  <verify>
    <automated>python -m pytest -q tests/test_new_baseline_contract.py tests/test_order_contract.py tests/test_writer.py; python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-new-baseline-readiness.json')); assert p['disposition'] in {'READY','STOP'}; assert p['historical_continuity_claimed'] is False; assert p['old_checkpoints_untouched'] is True; assert p['ready_for_01_02C'] is (p['disposition']=='READY'); print('new-baseline readiness receipt PASS')"</automated>
  </verify>
  <done>A bounded, explicitly identified epoch either produces deterministic Kafka/Landing/Bronze/Silver receipts and the sole `ready_for_01_02C=true` gate, or fails closed with legacy runtime restored and a durable STOP/rollback receipt; historical checkpoints and STOP artifacts remain untouched in both outcomes.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|---|---|
| Producer -> Kafka | Producer-supplied epoch, event ID, payload, and hash cross the untrusted message boundary. |
| Kafka container -> Docker volume | Broker log durability depends on the declared mount and log directory rather than container-local storage. |
| Kafka/Spark -> Landing/Bronze | Parsed event data and transport metadata cross into durable lakehouse storage. |
| Runtime state -> readiness receipt | Counts, hashes, offsets, and checkpoint evidence determine whether 01-02C may run. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|---|---|---|---|---|
| T-01-02B-NB-01 | Tampering | Kafka log storage | mitigate | Pin the broker log directory, mount `de_demo_kafka_data`, inspect the live mount, and record it in preflight/readiness evidence. |
| T-01-02B-NB-02 | Spoofing/Tampering | Producer event envelope | mitigate | Require explicit `source_epoch_id`, unique `event_id`, canonical sorted JSON, and SHA-256 hash; reject missing or mismatched lineage at the Spark boundary. |
| T-01-02B-NB-03 | Replay | Spark new-epoch reader | mitigate | Use an immutable epoch ID, an explicit post-approval per-partition tail, fresh named checkpoints, and duplicate event-id checks; do not silently consume historical offsets. |
| T-01-02B-NB-04 | Data loss/Denial of service | Spark checkpoints and Kafka offsets | mitigate | Preserve all four historical paths, keep `KAFKA_FAIL_ON_DATA_LOSS=true`, stop on unavailable offsets, and require exact bounded-window receipts before readiness. |
| T-01-02B-NB-05 | Repudiation | Evidence and approval gate | mitigate | Hash/count receipts include approval, source window, lineage digest, checkpoint map, and rollback disposition under the new-baseline namespace. |
| T-01-02B-NB-06 | Information disclosure | New-baseline receipts | accept | Existing demo data is local, non-sensitive, and receipts contain operational lineage only; no new external exposure is introduced. |
</threat_model>

<verification>
Run the focused contract suite before the checkpoint and again after the bounded epoch. Verify the Kafka volume mount and four new checkpoint roots with Docker/MinIO inspection, verify old checkpoint object listings and hashes are unchanged, and validate the readiness JSON schema/fields. A READY receipt must show equal valid-event counts/digests for Kafka, Landing, and Bronze, an expected deduplicated Silver count/digest, `historical_continuity_claimed=false`, and `ready_for_01_02C=true`; any other disposition is STOP and blocks 01-02C.
</verification>

<success_criteria>
- Kafka log data is stored at the explicitly configured log directory on `de_demo_kafka_data`.
- Focused tests prove epoch/event identity and canonical payload/hash preservation through Spark, Landing, and Bronze without a generic event framework.
- All four historical checkpoints and historical 01-02B/01-02B-R STOP artifacts remain untouched; four fresh checkpoint paths are named by the new epoch.
- The bounded fixture produces deterministic Kafka/Landing/Bronze/Silver counts and canonical digests in `02b-new-baseline-counts.json`.
- Exactly one approval checkpoint controls stateful start, and `02b-new-baseline-readiness.json` is the sole authorization for 01-02C; failed checks produce STOP/rollback and no authorization.
</success_criteria>

<output>
Create `.planning/phases/01-b2-controlled-rollout/01-02B-NB-SUMMARY.md` when done, recording either READY or STOP, the approval decision, epoch/checkpoint identities, evidence paths, and the fact that historical continuity was not claimed.
</output>
