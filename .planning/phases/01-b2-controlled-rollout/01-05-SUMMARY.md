---
phase: 01-b2-controlled-rollout
plan: 05
status: complete
disposition: CUTOVER_PASS
ready_for_01_06: true
completed: 2026-08-10
---

# 01-05 Summary — Persisted-Silver Gold Cutover

The green 01-04 M5 gate authorized one stateful recreation of
`iceberg-medallion`. The live runtime is now:

```text
SILVER_MODE=b2
GOLD_SOURCE=persisted_silver
SHADOW_COMPARE=1
```

Post-cutover evidence:

- 15 successful medallion rows in the cutover window
- 7 shadow comparisons, 0 mismatches
- 0 FF-14 conflicts and 0 in-flight work
- Bronze 218,965; Silver 218,964; Gold 123
- current Gold equals `build_gold(persisted Silver)`
- legacy business projection equals persisted Silver
- progress remains `next_sequence=259`, `work={}`
- forward completion-ledger fixture remains durable
- no Kafka/Spark checkpoints, volumes, or historical evidence were reset

The M4 integration cutover/rollback regression passed (`1 passed`). The live
rollback path was not invoked because no cutover invariant failed; the
approved `legacy/legacy/0` rollback tuple remains documented and tested.

Disposition: `CUTOVER_PASS`, `ready_for_01_06=true`. `01-06` was not executed.
