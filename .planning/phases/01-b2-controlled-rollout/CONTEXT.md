# Phase 1 Context: B2 Controlled Rollout

## Baseline

Start from verified repository checkpoint `89953fe` and the current persistent
state documented in `docs/remediation/S1.2-legacy-outbox-handoff.md`.

## Scope

This phase runs the accepted B2 architecture under controlled rollout:

1. preflight the clean handoff state;
2. run the first guarded `SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=1` canary and fail closed on runtime anomalies;
3. close the Iceberg REST SQLite catalog concurrency gap;
4. reconcile Kafka checkpoint offset loss without weakening fail-on-data-loss;
5. repeat the guarded B2 canary with fresh shadow evidence;
6. drain the 255 legitimate post-migration manifests;
7. evaluate the existing M5 cutover gate;
8. switch Gold to persisted Silver only after the gate is green;
9. collect O1 telemetry; and
10. decide D-3a, O2, or no-change.

## Guardrails

- Do not reopen completed M1–S1.2B decisions.
- Do not run D-3a or O2 pre-emptively.
- Keep Gold on legacy during both canary attempts and the drain.
- Stop and restore legacy configuration on shadow mismatch, FF-14, stuck
  progress, recovery anomaly, catalog lock, Kafka data-loss failure, or failed
  M5 evidence.
- Never delete or reset Spark checkpoints, Kafka topics, Iceberg tables, or the
  catalog volume as a recovery shortcut.
- `KAFKA_FAIL_ON_DATA_LOSS=true` is a safety invariant. A missing Kafka history
  requires continuity proof from business content and authoritative Bronze;
  otherwise the recovery disposition is STOP.
- The four Structured Streaming queries have independent checkpoint domains;
  batch IDs and offsets must not be treated as one global input window.
- Do not change physical layout, durable progress semantics, or orchestration
  ownership in the preflight or gap-closure plans.

## Current Readiness

```text
SAFE_STALE=0
LIVE_POST_MIGRATION=255
IN_FLIGHT_BLOCKED=0
BLOCKED=0
Bronze/Silver=218961/218961
Silver == accepted B2 projection
dbt=26/26 PASS
runtime=legacy/legacy/0
catalog=SQLite-backed and concurrency-blocked
kafka=checkpoint 218961, available offset 157; stream stopped fail-closed
```

Status: 01-02 failed safely. Execute 01-02A, then 01-02B, then 01-02C.
01-03 is blocked until 01-02C produces a fresh successful shadow cycle.
