---
phase: 01-b2-controlled-rollout
plan: 02B-R
recovery_id: 01-02B-R
type: execute
wave: 5
depends_on: [01-02B]
historical_predecessor_status: STOP
files_modified:
  - artifacts/b2-rollout/02b-recovery-preflight.json
  - artifacts/b2-rollout/02b-recovery-feasibility.json
  - artifacts/b2-rollout/02b-recovery-preservation.json
  - artifacts/b2-rollout/02b-recovery-checkpoint-recovery.log
  - artifacts/b2-rollout/02b-recovery-verification.json
autonomous: false
requirements: [CAN-01]
must_haves:
  truths:
    - "Historical 01-02B remains an immutable STOP result and is never rewritten as PASS."
    - "Recovery cannot proceed without Docker control-plane availability, Kafka cluster/topic identity, fresh evidence for all four checkpoints, and a durable canonical replay source."
    - "Completeness and identity/idempotency are independently proven before any new checkpoint epoch is created."
    - "Any failed or unknown gate produces STOP without deleting, resetting, or overwriting historical state."
    - "Only one stateful executor may run recovery, and KAFKA_FAIL_ON_DATA_LOSS remains true."
  artifacts:
    - path: "artifacts/b2-rollout/02b-recovery-preflight.json"
      provides: "Read-only control-plane, Kafka identity, checkpoint, durable-state, and replay-source inventory"
      contains: "docker_control_plane_available, cluster_id, checkpoint_paths, source_inventory"
    - path: "artifacts/b2-rollout/02b-recovery-feasibility.json"
      provides: "Independent completeness and identity/idempotency proof or explicit STOP"
      contains: "completeness_proven, identity_proven, idempotency_proven, disposition"
    - path: "artifacts/b2-rollout/02b-recovery-preservation.json"
      provides: "Before/after preservation barrier for historical checkpoints and durable outputs"
      contains: "historical_stop_immutable, old_checkpoint_preserved, destructive_actions"
    - path: "artifacts/b2-rollout/02b-recovery-checkpoint-recovery.log"
      provides: "Append-only command and stateful recovery audit log"
      contains: "KAFKA_FAIL_ON_DATA_LOSS=true and no forbidden recovery shortcut"
    - path: "artifacts/b2-rollout/02b-recovery-verification.json"
      provides: "Read-only post-recovery PASS/STOP receipt consumed by 01-02B-V"
      contains: "disposition, checkpoint_advanced, bronze_complete, duplicates_zero"
  key_links:
    - from: ".planning/phases/01-b2-controlled-rollout/01-02B-SUMMARY.md"
      to: "artifacts/b2-rollout/02b-recovery-preflight.json"
      via: "historical STOP evidence is referenced read-only"
      pattern: "STOP|old_checkpoint_preserved"
    - from: "artifacts/b2-rollout/02b-recovery-feasibility.json"
      to: "artifacts/b2-rollout/02b-recovery-verification.json"
      via: "only a complete, identity-safe source can authorize recovery"
      pattern: "completeness_proven|identity_proven|idempotency_proven"
    - from: "artifacts/b2-rollout/02b-recovery-verification.json"
      to: ".planning/phases/01-b2-controlled-rollout/01-02C-PLAN.md"
      via: "01-02C remains blocked unless recovery disposition is PASS"
      pattern: "PASS|STOP"
---

<objective>
Create a separate, fail-closed recovery boundary for the historical 01-02B
checkpoint/output epoch conflict. This plan may establish a new named epoch
only when read-only evidence proves both complete canonical source coverage and
non-colliding event identity/idempotency. It must never mutate or reinterpret
the historical 01-02B STOP result.
</objective>

<scope_boundary>
This plan is not a retry of 01-02B and does not amend, supersede, or overwrite
its evidence. Existing `artifacts/b2-rollout/02b-*` artifacts are read-only
inputs. New evidence uses the `02b-recovery-*` namespace. No execution of
01-02C is permitted until the separate post-recovery verification plan
01-02B-V records PASS.
</scope_boundary>

<tasks>

<task type="auto">
  <name>R1/R3: Capture preflight and preservation barrier</name>
  <files>artifacts/b2-rollout/02b-recovery-preflight.json, artifacts/b2-rollout/02b-recovery-preservation.json</files>
  <action>With producer and streaming services quiesced by the operator, inspect (without starting, stopping, resetting, or recreating state) Docker control-plane availability, container identity, Kafka cluster ID/topic identity/partition bounds, all four existing Spark checkpoint prefixes, Landing/Bronze/Silver/PostgreSQL/dead-letter boundaries, and candidate durable canonical replay sources. Reference the historical 01-02B STOP artifacts without modifying them. Before any stateful operation, write the preservation receipt with hashes/boundaries proving the historical STOP, old checkpoints, current Kafka evidence, durable outputs, and KAFKA_FAIL_ON_DATA_LOSS=true remain unchanged; require checkpoint_reset=false and destructive_actions=[]. Set both dispositions to STOP when any required observation is unavailable. Do not publish Kafka records or mutate MinIO, Iceberg, PostgreSQL, checkpoints, topics, or volumes.</action>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-recovery-preflight.json')); q=json.load(open('artifacts/b2-rollout/02b-recovery-preservation.json')); assert len(p['checkpoint_paths']) == 4; assert p['historical_stop_immutable'] is True; assert q['historical_stop_immutable'] is True; assert q['old_checkpoint_preserved'] is True; assert q['checkpoint_reset'] is False; assert q['destructive_actions'] == []; print('R1/R3 preflight preservation PASS')"</automated></verify>
  <done>R1/R3 records all required identities, checkpoint/state evidence, and an auditable preservation barrier, or records STOP with no runtime mutation.</done>
</task>

<task type="auto">
  <name>R2: Prove replay completeness and identity/idempotency</name>
  <files>artifacts/b2-rollout/02b-recovery-feasibility.json</files>
  <action>Evaluate each candidate durable source using canonical payload and hash coverage for the entire required new range. Separately prove source-generation/epoch identity so new events cannot collide with historical (topic, partition, offset) tuples, and prove that replay into Bronze is duplicate-safe. Counts, successful processing, order_id-only matching, or offset equality are insufficient. If either completeness or identity/idempotency is unproven, write disposition=STOP and do not authorize a new epoch.</action>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-recovery-feasibility.json')); assert p['disposition'] in {'AUTHORIZED','STOP'}; assert p['completeness_proven'] is False or p['identity_proven'] is True; assert p['idempotency_proven'] is False or p['identity_proven'] is True; print('R2 feasibility receipt shape PASS')"</automated></verify>
  <done>Completeness and identity/idempotency are independently recorded; an unprovable source leaves the recovery fail-closed.</done>
</task>

<task type="auto">
  <name>R4-R5: Create and execute one named recovery epoch</name>
  <files>artifacts/b2-rollout/02b-recovery-checkpoint-recovery.log</files>
  <action>Begin with an explicit human authorization checkpoint: do not continue unless R1/R3 and R2 receipts are PASS/AUTHORIZED and the reviewer confirms source-generation identity, completeness, idempotency, and preservation. Only then record a unique epoch name and expected canonical range, retain every historical checkpoint unchanged, and run the normal durable Spark recovery path with KAFKA_FAIL_ON_DATA_LOSS=true using one state-mutating executor. Capture commands, checkpoint advancement, source-generation metadata, Bronze receipts, idempotency outcomes, and rollback disposition. Never use startingOffsets=latest, failOnDataLoss=false, checkpoint deletion/reset, topic recreation/truncation, or destructive Docker volume reset. Any anomaly produces STOP and halts further work.</action>
  <verify><automated>python -c "from pathlib import Path; p=Path('artifacts/b2-rollout/02b-recovery-checkpoint-recovery.log'); assert p.exists(); t=p.read_text(encoding='utf-8'); assert 'KAFKA_FAIL_ON_DATA_LOSS=true' in t; assert 'startingOffsets=latest' not in t; assert 'checkpoint reset' not in t.lower(); print('R4-R5 recovery log safety PASS')"</automated></verify>
  <done>A named epoch is active only when authorized; the old epoch remains preserved and every stateful action is recorded.</done>
</task>

<task type="auto">
  <name>R6: Emit read-only post-recovery verification handoff</name>
  <files>artifacts/b2-rollout/02b-recovery-verification.json</files>
  <action>Read-only verify canonical source coverage, source-generation identity, Bronze completeness, zero duplicate business rows, checkpoint advancement from the named epoch, old checkpoint preservation, and runtime fail-on-data-loss configuration. Write exactly one disposition: PASS (eligible for separate 01-02B-V review) or STOP. Do not authorize 01-02C directly from this task.</action>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-recovery-verification.json')); assert p['disposition'] in {'PASS','STOP'}; assert p['duplicates_zero'] is True or p['disposition']=='STOP'; assert p['old_checkpoint_preserved'] is True; print('R6 verification receipt shape PASS')"</automated></verify>
  <done>A new recovery-specific receipt provides an auditable PASS/STOP handoff to 01-02B-V, while 01-02C remains blocked.</done>
</task>

</tasks>

<verification>
<automated>python -c "from pathlib import Path; p=Path('.planning/phases/01-b2-controlled-rollout/01-02B-PLAN.md').read_text(encoding='utf-8'); assert 'STOP' in p; assert Path('artifacts/b2-rollout/02b-recovery-preflight.json').parent.exists(); print('historical STOP boundary PASS')"</automated>
</verification>

<success_criteria>
The historical 01-02B STOP remains immutable. Recovery is executable only after
Docker/Kafka/checkpoint/source preflight, independent completeness and
identity/idempotency proofs, and a preservation barrier all pass. Otherwise the
plan produces STOP without state mutation. A successful recovery produces a
new-namespace verification receipt for the separate 01-02B-V plan; 01-02C is
not authorized by this plan alone.
</success_criteria>

<output>
Create `artifacts/b2-rollout/02b-recovery-verification.json` and hand off to a
separate post-recovery verification plan identified as `01-02B-V`.
</output>
