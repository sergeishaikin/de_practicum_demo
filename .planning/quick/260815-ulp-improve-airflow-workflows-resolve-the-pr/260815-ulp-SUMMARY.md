---
phase: quick
plan: 260815-ulp
status: complete
subsystem: airflow-lakehouse-operations
tags: [airflow, trino, iceberg, postgres, maintenance, staging-validation]
requires:
  - phase: 01-b2-controlled-rollout
    provides: b2/persisted_silver/1 runtime contract and immutable rollout evidence
provides:
  - Serialized, self-auditing mapped Iceberg maintenance with compatible snapshot expiry
  - Single-run batch DAG with exact four-table staging parity gate
  - Exact unique-run maintenance verifier and focused rejection coverage
affects: [lakehouse-maintenance, batch-pipeline, live-rollout-verification]
tech-stack:
  added: []
  patterns:
    - Per-map synchronous success/failure audit followed by exception re-raise
    - Exact run-ID verification with fail-closed classification
key-files:
  created: []
  modified:
    - dags/lakehouse_maintenance.py
    - dags/demo_core_marts_pipeline.py
    - scripts/dump_dag_structure.py
    - scripts/verify_maintenance_dag.py
    - tests/test_dags.py
    - tests/test_h1_runtime.py
    - tests/test_residual_remediation.py
    - tests/integration/test_iceberg_trino.py
    - README.md
    - docs/ARCHITECTURE.md
    - docs/CONFIGURATION.md
    - docs/DEVELOPMENT.md
    - docs/TESTING.md
key-decisions:
  - "Keep Trino 483, the persisted REST/JDBC catalog, retention, recovery, and data contracts unchanged; use explicit clean_expired_metadata=false."
  - "Restore b2/persisted_silver/1 only through the green Phase 01 M5 cutover mechanism, then execute each live proof exactly once."
requirements-completed: []
duration: 54 min
completed: 2026-08-15
---

# Quick Task 260815-ulp: Airflow Workflow Hardening Summary

**Compatible serialized Iceberg maintenance, exact staging parity, and exact-run verification are implemented and proven live under the authorized `b2/persisted_silver/1` runtime.**

## Status

`COMPLETE` — all code, focused tests, documentation, repository gates, and both authorized one-shot live proofs passed.

## Performance

- **Started:** 2026-08-15T21:41:49Z
- **Stopped:** 2026-08-15T22:35:00Z
- **Duration:** 54 min
- **Tasks:** 3 complete
- **Files modified:** 13

## Accomplishments

- Each `maintain_table` map captures its own before/after state, executes the three existing procedures once with `retries=0`, commits `ok`/`noop` or `failed:<operation>`, logs the exception/query ID, and re-raises failures.
- Airflow serializes maintenance map instances with `max_active_tis_per_dagrun=1`; the incompatible metadata cleanup flag is explicitly false without changing retention, recovery, targets, or runtime versions.
- The manual batch DAG allows one active run and inserts `validate_staging` between loading and core rebuild; all four CSV/staging pairs must be exact and non-empty.
- The verifier generates one collision-resistant `maintenance_verify_...` ID, passes it once to Airflow, queries only `where run_id = %s`, polls the exact DagRun, and rejects stale-equivalent, missing, duplicate, extra, or failed audit evidence.
- README and Airflow architecture/configuration/development/testing contracts now describe the implemented behavior and fail-closed operating rules.
- The green Phase 01 M5 receipt authorized restoration of the live medallion to `b2/persisted_silver/1`; exact one-shot maintenance and batch runs both succeeded without retries, clears, resets, or historical-evidence changes.

## Task Commits

1. **Task 1: Make mapped Iceberg maintenance compatible, serialized, and self-auditing** — `a9b8765`
2. **Task 2: Serialize the batch DAG and gate core rebuild on exact staging parity** — `97beacc`
3. **Task 3: Harden exact-run verification, align docs, and complete live proofs** — `2187c5e`

Planning artifacts, including this summary, are committed together by the orchestrator after independent verification.

## Verification Results

The shell PATH was refreshed from the existing machine and user PATH before canonical uv commands. `uv --version` reported `uv 0.12.5`; no tool or package was installed or updated.

| Command | Result |
|---|---|
| `uv run --locked pytest tests/test_residual_remediation.py -q` | PASS — 16 passed |
| `uv run --locked pytest tests/test_dags.py -m airflow -q` | PASS — 9 passed |
| `uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -q -s` | PASS — 1 passed against the isolated live namespace |
| `uv run --locked ruff check dags/demo_core_marts_pipeline.py scripts/dump_dag_structure.py tests/test_dags.py` | PASS |
| `uv run --locked pytest tests/test_h1_runtime.py -q` | PASS — 21 passed |
| `uv run --locked ruff check scripts/verify_maintenance_dag.py tests/test_h1_runtime.py` | PASS |
| `uv run --locked ruff check .` | PASS |
| `uv run --locked black --check .` | PASS — 52 files unchanged |
| `uv run --locked pytest` | PASS — 161 passed, 31 deselected |
| `uv run --locked ruff check dags --select AIR3 --preview` | PASS |
| `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet` | PASS |
| `docker exec de-demo-airflow airflow jobs check --job-type SchedulerJob --limit 1` | PASS — one alive job |
| `docker exec de-demo-airflow airflow jobs check --job-type TriggererJob --limit 1` | PASS — one alive job |
| `docker exec de-demo-airflow airflow jobs check --job-type DagProcessorJob --limit 1` | PASS — one alive job |
| `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | Expected baseline failure — 161 tests passed, 79.80% coverage vs 90%; no regression from documented baseline |

## Live Gate Evidence

### Authorized runtime transition and fresh preflight

- `artifacts/b2-rollout/04-m5-gate-result.json` was checked before mutation: `passed=true`, `failed_checks=[]`, and all seven evaluator checks were true.
- Following the owning `01-05-PLAN.md` mechanism, the process environment was set to `SILVER_MODE=b2`, `GOLD_SOURCE=persisted_silver`, and `SHADOW_COMPARE=1`; Compose config passed and only `iceberg-medallion` was force-recreated. The new container ID was `29e6ed281eb8...`.
- The running container reported exactly `b2/persisted_silver/1`; the first post-recreation medallion metric was `success` with `work_in_flight=0`, `ff14_conflicts=0`, and `shadow_mismatches=0`.
- Running and queued `lakehouse_maintenance` queries both returned `[]` immediately before the L1 trigger.
- Scheduler, triggerer, DAG processor, DagBag, Trino, REST catalog, PostgreSQL, and all three target tables were reachable.
- Retention remained `2h`, `retain_last=5`, recovery horizon `1h`, safety margin `15m`, file threshold `10MB`, and `clean_expired_metadata=false`.

### Fresh authoritative L1 baseline

The read-only PyIceberg inventory was rerun after the transition; the stale legacy-runtime inventory was not reused. Complete schemas, partition specs, and ordered snapshot-ID lists were printed. Key identifiers were:

| Table | UUID | Location | Metadata location | Schema ID | Spec ID | Logical rows | Snapshots |
|---|---|---|---|---:|---:|---:|---|
| `bronze.orders` | `3e26610c-7151-402d-bf46-fd43cfc91364` | `s3://de-practicum/warehouse/bronze/orders` | `.../metadata/05864-acf9eb04-f690-410a-9e01-f51014a01011.metadata.json` | 2 | 0 | 218966 | 5; first `3680198542225073251`, last `229477954253566003` |
| `silver.orders_clean` | `f26c2a91-8dc0-453c-8e6a-5ed72b3daf5c` | `s3://de-practicum/warehouse/silver/orders_clean` | `.../metadata/02140-9984b2b6-d66f-46cf-8744-1f8a531aa0fd.metadata.json` | 1 | 0 | 218964 | 202; first `8976677519313539521`, last `5810007697564845387` |
| `gold.orders_daily_metrics` | `b3efd680-1c48-48f7-81c1-ce72ea575a88` | `s3://de-practicum/warehouse/gold/orders_daily_metrics` | `.../metadata/02575-7f5055f6-0606-460b-b1e0-c4bdbdc7b1ac.metadata.json` | 0 | 0 | 123 | 205; first `8822928462905531200`, last `4418735396374786565` |

Bronze and Silver retained their day transform on `event_date`; Gold remained unpartitioned.

### L1 — exact maintenance proof

- The hardened verifier was invoked exactly once: `uv run --locked python scripts/verify_maintenance_dag.py`.
- Exact run ID: `maintenance_verify_20260815T222907391492Z_3be4ca723766`.
- The exact DagRun finished `success`; all three mapped tasks finished `success` on attempt 1.
- Exact audit rows were unique and successful: Bronze `5 -> 5` (`ok`), Silver `202 -> 165` (`ok`), Gold `205 -> 170` (`ok`).
- Post-run inventory retained all UUIDs, locations, schema IDs/definitions, spec IDs/definitions, and logical rows (`218966`, `218964`, `123`). Bronze remained at 5 snapshots; Silver retained 165; Gold was 170 at the audit and 172 at post-capture after two normal medallion snapshots.
- Runtime remained exactly `b2/persisted_silver/1`.
- Exact-run Airflow logs and time-bounded Trino/REST logs contained none of `remove-schemas`, `Cannot determine whether the commit was successful`, `CommitFailedException`, or generic internal errors.

### L2 — exact batch proof

- Pre-state CSV data rows were Orders `1000`, Order Items `1149`, Payments `1041`, Customers `1000`; staging counts matched all four exactly and were non-empty.
- Pre-state business values were Core Orders `1000`, Core Order Items/Wide Rows `1149`, Sales Days `463`, State Days `832`, payment totals `159040.39`, Gross Sales `136373.83`, Freight `22666.60`, and reconciliation diff/max-abs `0.00`.
- The batch DAG had no running/queued runs, was unpaused as the automation prerequisite, and was triggered exactly once.
- Exact run ID: `batch_verify_20260815T223250865259Z_6c9d0f4252d6`.
- The exact DagRun and all five tasks finished `success` on attempt 1. Its exact `marts.pipeline_runs` row was `success`, with `stg_orders=1000`, `stg_order_items=1149`, `core_order_items=1149`, `mart_sales_days=463`, zero duplicate/null rows, and `max_reconcile_diff=0.00`.
- Post-state CSV/staging counts and every recorded core/mart count and aggregate were equal to pre-state; payment and sales reconciliation remained exact.

### Final safety disposition

- **L1:** PASS, one trigger only.
- **L2:** PASS, one trigger only and only after L1 completed.
- **Retries/clears:** none. No task was cleared, replayed, backfilled, or retriggered.
- **Runtime:** the live container remains `b2/persisted_silver/1`.
- **Preservation:** no image/version, catalog registration, table identity/schema/spec, volume, checkpoint, replay, backfill, package, or historical Phase 01 evidence change occurred. `git status --short -- artifacts/b2-rollout .planning/phases/01-b2-controlled-rollout` was empty.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Refreshed stale process PATH to the already-installed canonical uv**

- **Found during:** Task 1 verification
- **Issue:** The inherited PATH resolved uv 0.10.7 while the repository requires 0.12.5.
- **Fix:** Prepended the current machine and user PATH, which resolved the existing WinGet uv 0.12.5 installation.
- **Files modified:** none
- **Verification:** `uv --version` returned 0.12.5 and all canonical locked commands ran.
- **Committed in:** N/A

### Authorized Continuation

**2. Restored the owning Phase 01 runtime after explicit user authorization**

- **Found during:** Task 3 continuation
- **Issue:** The live proof required `b2/persisted_silver/1`, while the running container was the rollback tuple.
- **Fix:** Verified the green M5 receipt, applied the documented process-environment tuple, and recreated only `iceberg-medallion` before taking a fresh baseline.
- **Files modified:** none; runtime container only
- **Verification:** Container inspection and post-transition metrics proved the required tuple and healthy state.
- **Committed in:** N/A

**Total deviations:** 1 auto-fixed blocking environment issue and 1 explicitly authorized runtime continuation. No package, dependency, schema, catalog, checkpoint, volume, or architectural change was added.

## Issues Encountered

- **Expected baseline:** Coverage remains 79.80% against the repository's 90% threshold while all 161 selected tests pass.

## Known Stubs

- `dags/demo_core_marts_pipeline.py:209-213` contains pre-existing instructional TODO comments for the already-implemented payment reconciliation exercise. They do not feed runtime data or block this task's staging gate.

## Threat Flags

None beyond the PLAN.md threat model. The changed trust surfaces are the exact four registered boundaries already covered by T-QUICK-01 through T-QUICK-04.

## Self-Check: PASSED

All 13 planned files and the summary exist. Commits `a9b8765`, `97beacc`, and
`2187c5e` resolve to commits on `feature/extended-local-stack`. The summary
records both exact live run IDs, their successful task/audit evidence, the
before/after invariants, and the absence of retries or clears.
