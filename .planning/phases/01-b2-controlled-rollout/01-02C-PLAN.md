---
phase: 01-b2-controlled-rollout
plan: 02C
type: execute
wave: 7
depends_on: [01-02A, 01-02B-NB]
files_modified:
  - artifacts/b2-rollout/02c-canary-runtime.txt
  - artifacts/b2-rollout/02c-canary-tests.log
  - artifacts/b2-rollout/02c-canary-receipt.json
  - artifacts/b2-rollout/02c-canary-rollback.txt
autonomous: true
requirements: [CAN-01]
must_haves:
  truths:
    - "The repeated canary starts only after both catalog concurrency and Kafka continuity gates are green."
    - "B2 Silver runs with legacy Gold and shadow enabled; no persisted-Silver Gold cutover occurs in this plan."
    - "Any mismatch, FF-14, stuck progress, recovery anomaly, offset-loss failure, or catalog lock restores legacy/legacy/0 without data reset."
  artifacts:
    - path: "artifacts/b2-rollout/02c-canary-receipt.json"
      provides: "Fresh canary evidence after runtime gap closure"
      contains: "successful_shadow_cycle"
    - path: "artifacts/b2-rollout/02c-canary-rollback.txt"
      provides: "Fail-closed rollback evidence"
      contains: "legacy/legacy/0"
  key_links:
    - from: "artifacts/b2-rollout/02a-catalog-recovery.json"
      to: "artifacts/b2-rollout/02c-canary-receipt.json"
      via: "catalog green precondition"
      pattern: "passed"
    - from: "artifacts/b2-rollout/02b-new-baseline-readiness.json"
      to: "artifacts/b2-rollout/02c-canary-receipt.json"
      via: "new-epoch baseline readiness precondition"
      pattern: "ready_for_01_02c|disposition"
---

<objective>
Repeat the controlled B2 canary after both runtime blockers are closed.

Purpose: prove that the previous failure was removed rather than hidden, while keeping Gold on the legacy projection and preserving a clean rollback boundary.
</objective>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/01-b2-controlled-rollout/CONTEXT.md
@artifacts/b2-rollout/02a-catalog-recovery.json
@artifacts/b2-rollout/02b-new-baseline-readiness.json
@artifacts/b2-rollout/02-canary-receipt.json
@.planning/phases/01-b2-controlled-rollout/01-02-PLAN.md
@tests/test_m5_fitness_functions.py
@tests/test_b2_medallion.py
@tests/integration/test_m3_b2_recovery.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Apply the guarded repeat-canary tuple</name>
  <files>artifacts/b2-rollout/02c-canary-runtime.txt</files>
  <action>Require 02A passed=true, 02b-new-baseline-readiness disposition=READY with ready_for_01_02C=true, and restored services healthy. Set only SILVER_MODE=b2, GOLD_SOURCE=legacy, SHADOW_COMPARE=1; validate Compose and inspect the running container. Confirm orders-streaming remains fail-on-data-loss=true and no persisted-Silver Gold source is active. Capture runtime, service health, catalog backend, checkpoint epoch, and pre-canary progress.</action>
  <verify><automated>python -c "import json; a=json.load(open('artifacts/b2-rollout/02a-catalog-recovery.json')); b=json.load(open('artifacts/b2-rollout/02b-new-baseline-readiness.json')); assert a['passed'] is True and b['disposition']=='READY' and b['ready_for_01_02C'] is True; print('repeat canary preconditions PASS')"; docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config --quiet; docker inspect de-demo-iceberg-medallion --format '{{range .Config.Env}}{{println .}}{{end}}' | Select-String 'SILVER_MODE=b2|GOLD_SOURCE=legacy|SHADOW_COMPARE=1'</automated></verify>
  <done>The live services report the exact b2/legacy/1 canary tuple with both gap receipts green.</done>
</task>

<task type="auto">
  <name>Task 2: Run and evaluate one fresh shadow cycle</name>
  <files>artifacts/b2-rollout/02c-canary-tests.log, artifacts/b2-rollout/02c-canary-receipt.json, artifacts/b2-rollout/02c-canary-rollback.txt</files>
  <action>Run the focused B2, M3 recovery, M4 Gold, medallion, writer, and order-contract tests; observe fresh medallion metrics until at least one successful non-empty shadow cycle is recorded. Require shadow_mismatches=0, ff14_conflicts=0, work_in_flight=0 at convergence, no catalog lock error, no Kafka data-loss error, and no progress anomaly. On any failure stop the service and restore legacy/legacy/0; preserve all receipts and never reset progress, outbox, checkpoints, or Iceberg tables.</action>
  <verify><automated>python -m pytest -q --basetemp .pytest-b2-repeat tests/test_m5_fitness_functions.py tests/test_b2_medallion.py tests/test_m4_gold.py tests/test_medallion.py tests/test_writer.py tests/test_order_contract.py tests/integration/test_m3_b2_recovery.py -s; docker exec de-demo-postgres psql -U app -d dwh -At -F '|' -c "select count(*),coalesce(sum(shadow_comparisons),0),coalesce(sum(shadow_mismatches),0),coalesce(sum(ff14_conflicts),0),coalesce(max(work_in_flight),0) from marts.lakehouse_metrics where source='medallion' and status='success'"; python -c "import json; p=json.load(open('artifacts/b2-rollout/02c-canary-receipt.json')); assert p['successful_shadow_cycle'] is True and p['shadow_mismatches']==0 and p['ff14_conflicts']==0 and p['unresolved_progress']==0; print('repeat canary PASS')"</automated></verify>
  <done>Fresh B2 canary evidence is green with legacy Gold still active; otherwise a durable fail-closed rollback receipt blocks 01-03.</done>
</task>

</tasks>

<success_criteria>
02C is the only authorization to proceed to drain: it requires fresh successful shadow evidence after catalog and Kafka recovery, with zero correctness/recovery failures and legacy Gold still selected.
</success_criteria>

<output>Create .planning/phases/01-b2-controlled-rollout/01-02C-SUMMARY.md when done.</output>
