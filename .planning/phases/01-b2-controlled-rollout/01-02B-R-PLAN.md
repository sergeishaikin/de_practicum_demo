---
phase: 01-b2-controlled-rollout
plan: 02B-R
recovery_id: 01-02B-R
type: execute
wave: 5
depends_on: [01-02B]
historical_predecessor_status: STOP
status: stop
result: RECOVERY_NOT_PROVEN
r1_status: completed
r2_status: failed
r3_r6_status: not_applicable
files_modified:
  - artifacts/b2-rollout/02b-recovery-preflight.json
  - artifacts/b2-rollout/02b-recovery-feasibility.json
autonomous: true
requirements: [CAN-01]
must_haves:
  truths:
    - "Historical 01-02B remains an immutable STOP result and is never rewritten as PASS."
    - "Read-only evidence captures the current Kafka epoch, four checkpoints, durable outputs, and replay-source inventory."
    - "Missing canonical source and epoch-safe identity produce RECOVERY_NOT_PROVEN rather than a recovery attempt."
    - "No checkpoint, topic, output, or runtime state is mutated by this plan."
  artifacts:
    - path: "artifacts/b2-rollout/02b-recovery-preflight.json"
      provides: "Read-only Docker/Kafka/checkpoint/output/source inventory"
      contains: "cluster_id, checkpoint_paths, source_inventory"
    - path: "artifacts/b2-rollout/02b-recovery-feasibility.json"
      provides: "Final RECOVERY_NOT_PROVEN feasibility decision"
      contains: "completeness_proven, identity_proven, idempotency_proven, disposition"
---

<objective>
Close the bounded historical recovery attempt as STOP. R1 read-only evidence
is complete; R2 cannot prove a canonical replay source or epoch-safe identity.
No recovery is performed and no post-recovery verification plan is created.
</objective>

<scope_boundary>
This plan is a terminal feasibility result, not a retry of historical 01-02B.
Historical 01-02B remains immutable STOP evidence. R3-R6 are not applicable
because recovery was never authorized or executed. A future new-epoch baseline
must be planned separately and must not be called historical recovery.
</scope_boundary>

<tasks>

<task type="auto">
  <name>R1: Capture read-only recovery preflight</name>
  <files>artifacts/b2-rollout/02b-recovery-preflight.json</files>
  <action>Capture Docker/Kafka identity, topic bounds, persistence configuration, all four checkpoint states, Landing/Bronze/Silver/PostgreSQL/DLQ boundaries, and every candidate durable source. Preserve all historical 02b artifacts and runtime state. Do not start/stop services, publish records, reset checkpoints, or mutate data.</action>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-recovery-preflight.json')); assert len(p['checkpoint_paths']) == 4; assert p['historical_stop_immutable'] is True; assert p['old_checkpoint_preserved'] is True; assert p['destructive_actions'] == []; print('R1 preflight PASS')"</automated></verify>
  <done>R1 evidence is captured read-only with exact identity, offset, checkpoint, output, and source boundaries.</done>
</task>

<task type="auto">
  <name>R2: Decide canonical replay feasibility</name>
  <files>artifacts/b2-rollout/02b-recovery-feasibility.json</files>
  <action>Independently evaluate canonical completeness, payload/hash equivalence, source-generation identity, and duplicate-safe Bronze replay. Counts, successful processing, order_id-only matching, and numeric offsets are insufficient. Because no durable canonical source or epoch-safe identity is proven, write disposition=RECOVERY_NOT_PROVEN, leave all recovery fields false, and stop the plan.</action>
  <verify><automated>python -c "import json; p=json.load(open('artifacts/b2-rollout/02b-recovery-feasibility.json')); assert p['disposition']=='RECOVERY_NOT_PROVEN'; assert p['completeness_proven'] is False and p['identity_proven'] is False and p['idempotency_proven'] is False; assert p['bounded_recovery_performed'] is False; assert p['old_checkpoint_preserved'] is True; print('R2 STOP PASS')"</automated></verify>
  <done>01-02B-R closes as STOP/RECOVERY_NOT_PROVEN; no checkpoint epoch, replay, or verification plan is authorized.</done>
</task>

</tasks>

<verification>
<automated>python -c "from pathlib import Path; p=Path('.planning/phases/01-b2-controlled-rollout/01-02B-PLAN.md').read_text(encoding='utf-8'); assert 'STOP' in p; assert Path('artifacts/b2-rollout/02b-recovery-feasibility.json').exists(); print('historical STOP boundary PASS')"</automated>
</verification>

<success_criteria>
R1 is complete, R2 fails closed with RECOVERY_NOT_PROVEN, R3-R6 are not
applicable, and all historical checkpoints/evidence remain untouched. Future
progress requires an explicit new-epoch baseline plan rather than historical
recovery.
</success_criteria>

<output>
Create `01-02B-R-SUMMARY.md` with the terminal STOP result and evidence links.
</output>
