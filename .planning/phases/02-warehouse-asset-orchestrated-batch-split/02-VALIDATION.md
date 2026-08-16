---
phase: 02
slug: warehouse-asset-orchestrated-batch-split
date: 2026-08-16
nyquist_compliant: true
wave_0_complete: true
---

# Phase 02 Validation Strategy

## Requirement matrix

| Requirement | Automated evidence | Live evidence |
|---|---|---|
| ORCH-01 | DagBag asserts two IDs, manual/Asset schedules, metadata, run limits, retries and timeouts | health smoke shows both parsed |
| ORCH-02 | BDD and regression tests execute exact staging parity and guard unchanged rebuild SQL | ingestion exact task states/counts |
| ORCH-03 | BDD executes queryability/count success including zero and readiness failure with no yielded metadata | core Asset events appear only for successful run |
| ORCH-04 | DagBag outlets plus callable Metadata assertions and provenance tests | exact event `extra` and `source_run_id` |
| ORCH-05 | migration shape/idempotency test and schema documentation assertions | live column, index, and historical NULL proof |
| ORCH-06 | DagBag/BDD assert marts readiness, reconciliation, publication, and audit while views remain views | downstream exact task states and views queryable |
| ORCH-07 | dependency/TaskGroup assertions and exact audit classifier | `pipeline_runs.run_id`/`ingestion_run_id` pair |
| ORCH-08 | full unit, AIR3, DagBag, BDD, migration, verifier, regression, Compose suite | one-shot E2E plus read-only receipt replay |

## Fail-closed runtime gate

The verifier may trigger `warehouse_orders_ingestion` once only after checking
there are no active or queued runs for either Phase 02 DAG. It never manually
triggers `warehouse_marts_validation`. It correlates the downstream run through
the exact `asset_event` source run and requires one unambiguous audit row.
Ambiguous CLI/database outcomes stop the gate without a retry.

## Commands

```bash
uv run --locked ruff check .
uv run --locked black --check .
uv run --locked pytest
uv run --locked ruff check dags --select AIR3 --preview
uv run --locked pytest tests/test_h1_runtime.py
uv run --locked pytest tests/test_dags.py -m airflow
uv run --locked pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet
```

The live verifier command and receipt identifiers are recorded in the phase
summary and verification report. The pre-existing coverage threshold gap is
reported but is not remediated by this phase.

## Validation Audit 2026-08-16

| Metric | Count |
|--------|-------|
| Requirements audited | 8/8 COVERED |
| Recorded decisions audited | 14/14 COVERED |
| Gaps found | 0 |
| Tests added by audit | 0 |
| Manual-only behaviors | 0 |

The GSD Nyquist auditor cross-referenced ORCH-01 through ORCH-08 and D-01
through D-14 against DagBag, unit, Gherkin, migration integration, verifier,
live receipt, and read-only receipt-replay evidence. The later code review
hardening added ambiguity and matching-payment scenarios, increasing rather
than weakening this coverage. Phase 02 is Nyquist-compliant.
