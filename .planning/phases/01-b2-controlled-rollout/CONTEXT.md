# Phase 1 Context: B2 Controlled Rollout

## Baseline

Start from verified repository checkpoint `89953fe` and the current persistent
state documented in `docs/remediation/S1.2-legacy-outbox-handoff.md`.

## Scope

This phase runs the accepted B2 architecture under controlled rollout:

1. preflight the clean handoff state;
2. run `SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=1`;
3. drain the 255 legitimate post-migration manifests;
4. evaluate the existing M5 cutover gate;
5. switch Gold to persisted Silver only after the gate is green;
6. collect O1 telemetry; and
7. decide D-3a, O2, or no-change.

## Guardrails

- Do not reopen completed M1–S1.2B decisions.
- Do not run D-3a or O2 pre-emptively.
- Keep Gold on legacy during canary.
- Stop and restore legacy configuration on shadow mismatch, FF-14, stuck
  progress, recovery anomaly, or failed M5 evidence.
- Do not change physical layout, durable progress semantics, or orchestration
  ownership in the preflight plan.

## Current Readiness

```text
SAFE_STALE=0
LIVE_POST_MIGRATION=255
IN_FLIGHT_BLOCKED=0
BLOCKED=0
Bronze/Silver=218961/218961
Silver == accepted B2 projection
dbt=26/26 PASS
```

Status: ready to plan 01-01.
