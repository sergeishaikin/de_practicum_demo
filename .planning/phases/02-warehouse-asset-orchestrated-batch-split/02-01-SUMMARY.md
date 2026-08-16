---
phase: 02-warehouse-asset-orchestrated-batch-split
plan: 01
subsystem: airflow-orchestration
tags: [airflow-3.3.1, assets, postgres, pytest-bdd, provenance]
requires:
  - phase: quick-260815-ulp
    provides: Airflow 3.3.1 LocalExecutor runtime and exact-run verifier baseline
provides:
  - Manual warehouse ingestion DAG with successful-only core Asset publication
  - Asset-triggered marts validation/publication DAG with native source provenance
  - Additive indexed ingestion_run_id audit migration
  - Unit, DagBag, Gherkin, integration, and exact live receipt evidence
affects: [warehouse-batch, airflow-ui, pipeline-audit, phase-2-medallion-seed]
tech-stack:
  added: []
  patterns: [terminal Asset publisher, native AssetEvent provenance, fail-closed exact-run receipt]
key-files:
  created:
    - dags/warehouse_orders.py
    - db/init/007_pipeline_runs_ingestion_provenance.sql
    - scripts/verify_warehouse_asset_flow.py
    - tests/integration/test_warehouse_asset_provenance.py
  modified:
    - db/init/004_smoke_objects.sql
    - scripts/bootstrap_stack.py
    - tests/test_dags.py
    - tests/test_h1_runtime.py
    - tests/features/airflow_workflow_behavior.feature
    - tests/e2e/test_airflow_run_receipts.py
key-decisions:
  - "Keep ingestion manual and schedule only warehouse_marts_validation from core.orders."
  - "Keep marts as views and preserve the complete 10_rebuild_core.sql transaction."
  - "Keep run_id as the downstream primary key and add nullable, non-unique-indexed ingestion_run_id."
patterns-established:
  - "Only a terminal task declares scheduling outlets after all readiness gates pass."
  - "Correlation uses AssetEvent.source_dag_run.run_id and rejects ambiguous event collections."
requirements-completed: [ORCH-01, ORCH-02, ORCH-03, ORCH-04, ORCH-05, ORCH-06, ORCH-07, ORCH-08]
duration: 1h 12m
completed: 2026-08-16
---

# Phase 02: Warehouse Asset-Orchestrated Batch Split Summary

**A manual ingestion DAG now publishes verified core row counts into a real Airflow Asset boundary that automatically starts marts validation and records exact source/downstream provenance.**

## Performance

- **Duration:** 1h 12m
- **Started:** 2026-08-16T09:57:38Z
- **Completed:** 2026-08-16T11:09:52Z
- **Tasks:** 3/3 complete
- **Requirements:** 8/8 complete

## Accomplishments

- Replaced `demo_core_marts_pipeline` with manual
  `warehouse_orders_ingestion` and Asset-triggered
  `warehouse_marts_validation`, using honest display metadata and TaskGroups.
- Preserved staging parity, the full core/marts SQL transaction, payment
  reconciliation, audit metrics, and all marts views without new DQ rules.
- Added additive provenance storage and a one-shot verifier that follows the
  native source event to the automatic consumer and exact audit row.
- Proved failure/ambiguity semantics through 11 Gherkin scenarios, DagBag,
  unit classifiers, live migration, exact runtime, and read-only replay tests.

## Task Commits

1. **Task 1: Split warehouse DAG at the Asset boundary** — `b8dad76`
2. **Task 2: Add migration, verifier, and layered tests** — `8a1db1a`
3. **Review hardening: close six correctness/reliability findings** — `c202860`
4. **Task 3: Make the learner Airflow check executable** — `8ae7d93`
5. **Task 3: Align operational and schema documentation** — `171f0b5`

**Plan metadata:** `50b00c7`

## Runtime Evidence

- Source: `warehouse_orders_ingestion` /
  `warehouse_ingestion_verify_20260816T103440557566Z_f3cb30260fd9`
  (`manual`, `success`).
- Asset events: `core.orders` event 31 with `row_count=1000` and
  `core.order_items` event 32 with `row_count=1149`, both from
  `core.publish_core_assets` and the exact source run.
- Consumer: `warehouse_marts_validation` /
  `asset_triggered__2026-08-16T10:35:04.448658+00:00_PJHWpBUF`
  (`asset_triggered`, `success`).
- Audit: downstream `run_id`, exact source `ingestion_run_id`, status
  `success`; nine tasks succeeded once with zero retries.
- Warehouse snapshot before/after was identical: staging
  `1000/1149/1041/1000`, core `1000/1149`, 463 sales days, payment totals
  `159040.39`, max reconciliation difference `0.00`.
- Five historical audit rows retained `ingestion_run_id IS NULL`; the index is
  non-unique and all four marts relations remain views.

## Decisions Made

- Asset `extra` contains only integer row counts; source IDs remain native
  Airflow provenance.
- Multiple `core.orders` source events are rejected rather than selecting an
  arbitrary latest event.
- The verifier unpauses only the Asset consumer and never manually triggers it.
- No dependency, service, scheduler, task runner, or test framework was added.

## Deviations from Plan

### Auto-fixed Issues

1. **PostgreSQL outage caused by a disposable Spark worker writable layer**
   - Verified the worker had no named-volume state, recreated only
     `spark-worker`, and released the oversized writable layer without pruning
     images, volumes, Kafka, MinIO, PostgreSQL, or Iceberg state.

2. **Existing-volume view migration initially changed column position**
   - The live idempotency test exposed PostgreSQL's view-column constraint.
     Appending `ingestion_run_id` to the view contract made both new and
     existing volumes safe; applying the migration twice passes.

3. **Airflow standalone heartbeats stayed stale after the database outage**
   - Restarted only the Airflow service. Metadata persisted; scheduler,
     triggerer, DAG processor, and metadatabase returned healthy.

4. **Standard review found six evidence/correlation weaknesses**
   - Fixed ambiguous source selection, false E2E skips, unspecific row-count
     certification, credential fallback/config drift, unnecessary ingestion
     unpause, and tautological historical NULL evidence. Re-review is clean.

5. **Learner `airflow tasks test` returned zero after an internal skipped task**
   - Replaced that false-positive command with the existing pytest-bdd actual
     callable scenario; the checker now selects and passes one real feature test.

**Total deviations:** 5 correctness/blocking fixes. All were required to make
the requested evidence truthful; none changed business or storage semantics.

## Known Unrelated Baseline

The existing coverage command ran after implementation: all 186 selected fast
tests passed, but `iceberg/` coverage remains 79.80% against 90%, exit 1. The
threshold was not lowered and no unrelated coverage tests were added. The
extended status also reports an unrelated `superset-mcp` health issue; all
Phase 02 dependencies and the exact warehouse flow were healthy.

## User Setup Required

None. The existing ignored `.env` and persistent PostgreSQL volume were used;
the idempotent migration is also wired into normal bootstrap.

## Next Phase Readiness

Phase 02 is ready to merge. Airflow-owned medallion remains only a future
evaluation seed, not an approved requirement or continuation of this phase.

---
*Phase: 02-warehouse-asset-orchestrated-batch-split*
*Completed: 2026-08-16*
