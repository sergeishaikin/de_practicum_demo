---
phase: quick
slug: 260815-ulp-improve-airflow-workflows-resolve-the-pr
status: passed
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-15
---

# Quick Task 260815-ulp — Validation Strategy

> Nyquist validation contract for the Airflow maintenance and batch-workflow remediation. This document plans evidence only; it does not authorize retries after ambiguous stateful commits.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 from the locked project environment; Airflow DagBag checks run in the existing Airflow 3.3.1 container |
| **Config file** | `pytest.ini`, `pyproject.toml`, `uv.lock` |
| **Quick run command** | `uv run --locked pytest tests/test_residual_remediation.py tests/test_h1_runtime.py -q` |
| **DAG run command** | `uv run --locked pytest tests/test_dags.py -m airflow -q` |
| **Read-only receipt command** | `AIRFLOW_RECEIPT_E2E=1 uv run --locked pytest tests/e2e/test_airflow_run_receipts.py -m "e2e and airflow" -q` (PowerShell: set the environment variable with `$env:` first) |
| **Focused integration command** | `uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -q -s` |
| **Full fast suite** | `uv run --locked pytest` |
| **Live maintenance gate** | `uv run --locked python scripts/verify_maintenance_dag.py`, exactly once after the required pre-state capture |
| **Infrastructure additions** | None — existing pytest, Compose services, verifier, Airflow, Trino, Iceberg REST, and PostgreSQL cover all requirements |

## Must-Have IDs

| ID | Observable truth from PLAN.md |
|----|-------------------------------|
| MH-01 | Maintenance keeps operation order, retries=0, retention/recovery settings, targets, and data semantics while using explicit `clean_expired_metadata=false` on the unchanged Trino/catalog runtime. |
| MH-02 | Every mapped table task durably records its own success/failure and re-raises failures; mapped maintenance is serialized by native Airflow task concurrency. |
| MH-03 | The batch DAG admits one active run and blocks core/marts unless all four configured CSV/staging pairs are exact and non-empty. |
| MH-04 | The verifier accepts only one exact unique maintenance run with exactly one `ok`/`noop` row for each expected table. |
| MH-05 | Authorized one-shot live proofs preserve table identity, logical semantics, `b2/persisted_silver/1`, and immutable historical evidence, with no retry after ambiguity. |

## Sampling Rate

- **After Task 1 implementation:** Run the focused fast remediation test, live DagBag test, and isolated Trino/Iceberg maintenance procedure test.
- **After Task 2 implementation:** Run DAG lint and the live DagBag test before any batch trigger.
- **After Task 3 implementation:** Run verifier unit coverage and lint before capturing live pre-state.
- **Before completion:** Run the repository completion gate, then the authorized maintenance and batch live gates in the fail-closed order below.
- **Maximum fast-feedback target:** 60 seconds for host unit/lint checks; container, integration, and live checks are explicitly separate stateful gates and may run longer.

## Per-Task Verification Map

| Task ID | Plan | Wave | Must-Have | Threat Ref | Behavior Protected | Test Type | Automated / Live Command | File Exists | Status |
|---------|------|------|-----------|------------|--------------------|-----------|--------------------------|-------------|--------|
| 260815-ulp-01a | 260815-ulp | 1 | MH-01 | T-QUICK-01 | Explicit compatible expiry flag, unchanged retention/recovery exports, and no retry path | focused unit/source contract | `uv run --locked pytest tests/test_residual_remediation.py -q` | ✅ | ✅ green |
| 260815-ulp-01b | 260815-ulp | 1 | MH-01 | T-QUICK-01 | Real Trino procedure accepts explicit false flag and preserves logical row count/snapshot assertions | isolated integration | `uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -q -s` | ✅ | ✅ green |
| 260815-ulp-01c | 260815-ulp | 1 | MH-02 | T-QUICK-01, T-QUICK-02 | One mapped task, exact task concurrency=1, max_active_runs=1, retries=0, and no failure-masking reducer | Airflow DagBag | `uv run --locked pytest tests/test_dags.py -m airflow -q` | ✅ | ✅ green |
| 260815-ulp-02a | 260815-ulp | 1 | MH-03 | T-QUICK-03, T-QUICK-04 | Batch max_active_runs=1, validation task placement, four inlets/zero outlets, unchanged downstream assets | Airflow DagBag | `uv run --locked pytest tests/test_dags.py -m airflow -q` | ✅ | ✅ green |
| 260815-ulp-02b | 260815-ulp | 1 | MH-03 | T-QUICK-03 | Python/Airflow source remains lint-clean | static | `uv run --locked ruff check dags/demo_core_marts_pipeline.py scripts/dump_dag_structure.py tests/test_dags.py` | ✅ | ✅ green |
| 260815-ulp-03a | 260815-ulp | 1 | MH-04 | T-QUICK-02, T-QUICK-04 | Unique run ID propagation and rejection of missing, duplicate, extra, stale-equivalent, or failed rows | unit | `uv run --locked pytest tests/test_h1_runtime.py -q` | ✅ | ✅ green |
| 260815-ulp-03b | 260815-ulp | 1 | MH-01, MH-02, MH-04, MH-05 | Exact successful maintenance DagRun/audit and preserved pre/post catalog contract | authorized live | `uv run --locked python scripts/verify_maintenance_dag.py` exactly once after baseline capture | ✅ | ✅ green |
| 260815-ulp-03c | 260815-ulp | 1 | MH-03, MH-05 | Exact non-empty four-table parity and successful unchanged business results | authorized live | Trigger `demo_core_marts_pipeline` once with `batch_verify_<UTC>_<suffix>` and query that exact `marts.pipeline_runs.run_id` | N/A | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

## Resolved Staging Scope

The validation boundary is exact and closed: for every one of the four existing `STG_LOADS`, the CSV data-record count and committed staging `count(*)` must be equal and greater than zero. No additional staging-domain rule is introduced. Existing payment reconciliation, duplicate/null-key checks, mart reconciliation, and final pipeline audit remain unchanged and are verified by their current downstream tasks/tests.

## Live-Gate Preconditions

All of the following must be true before either live trigger:

- Static, host-unit, AIR3 lint, live DagBag, Compose-config, and focused integration checks have completed and their exact results are recorded.
- Airflow scheduler, triggerer, DAG processor, and DagBag are healthy; the target DAG is parsed and unpaused.
- Any active `lakehouse_maintenance` DagRun has finished. Do not clear or rerun its tasks.
- Runtime inspection confirms `SILVER_MODE=b2`, `GOLD_SOURCE=persisted_silver`, and `SHADOW_COMPARE=1`; no environment, checkpoint, volume, catalog registration, table ownership, or stateful image/version change is permitted.
- For `bronze.orders`, `silver.orders_clean`, and `gold.orders_daily_metrics`, capture table UUID, location, metadata location, current schema/schema ID, partition spec/spec ID, logical row count, snapshot IDs/count, and the retention/recovery contract.
- Preserve historical 01-02B, 01-02B-R, and 01-03 evidence unchanged. No reset, replay, backfill, fabricated identity, or cleanup is authorized.

## Authorized Live Gates

### Gate L1 — Maintenance exact-run proof

1. The verifier generates and prints one collision-resistant ID in the form `maintenance_verify_<UTC timestamp>_<suffix>`.
2. That exact ID is passed once to `airflow dags trigger -r`; the same value is used for DagRun polling and the parameterized `marts.maintenance_runs where run_id = %s` query.
3. Require one successful exact DagRun and exactly three audit rows: one unique row for each configured target and statuses only `ok`/`noop`. Reject missing, extra, duplicate, failed, broad-window, or uncertain results.
4. Re-capture the catalog inventory. UUID, location, current schema/spec, logical row counts, retention/recovery settings, and `b2/persisted_silver/1` must be unchanged. Snapshot IDs/counts may change only as expected from maintenance.
5. Exact-run Airflow/Trino/REST logs must contain none of `remove-schemas`, `Cannot determine whether the commit was successful`, `CommitFailedException`, or generic internal errors.

**Fail-closed rule:** If trigger creation or any commit-capable task is ambiguous, stop immediately. Do not trigger again, clear a task, rerun a map index, or run orphan cleanup. Record the exact operation and Trino query ID, then inspect REST logs, the authoritative metadata pointer, and snapshot history against pre-state. A second trigger requires separate authorization only after the first outcome is classified.

### Gate L2 — Batch exact-run proof

Run only after Gate L1 succeeds and its post-state comparison is complete.

1. Capture all four CSV data-row counts, staging counts, core/mart counts, and reconciliation totals.
2. Create one unique `batch_verify_<UTC timestamp>_<suffix>` ID and trigger `demo_core_marts_pipeline` exactly once with it.
3. Query only that exact `marts.pipeline_runs.run_id`; require `success`.
4. Require each CSV/staging pair to be equal and non-empty and require unchanged business counts/aggregates for unchanged CSV inputs.
5. Record the exact ID, task states, audit row, and pre/post comparison. A failed gate remains failed; do not conceal it with a different run ID.

## Repository Completion Gate

| Gate | Command | Required interpretation |
|------|---------|-------------------------|
| Ruff | `uv run --locked ruff check .` | Must pass. |
| Black | `uv run --locked black --check .` | Must pass. |
| Fast suite | `uv run --locked pytest` | Must pass. |
| Airflow 3 lint | `uv run --locked ruff check dags --select AIR3 --preview` | Must pass. |
| Runtime contract | `uv run --locked pytest tests/test_h1_runtime.py` | Must pass. |
| DagBag | `uv run --locked pytest tests/test_dags.py -m airflow` | Must pass against the live Airflow container. |
| Integration | `uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -s` | Must pass against the real isolated integration namespace. |
| Compose | `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet` | Must pass. |
| Coverage baseline | `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | Run and report exactly. The documented baseline is 150 passing fast tests with 79.80% coverage and exit 1 against 90%; do not lower the threshold or add unrelated tests. Any further regression is a blocker. |

## Wave 0 Requirements

Existing infrastructure covers every must-have. No Wave 0 test scaffold, dependency, fixture framework, wrapper, service, or runner is required.

## Manual-Only Verifications

None. The stateful gates require live services but are agent-executable and evidence-backed; they are not delegated to a human checkpoint.

## Validation Sign-Off

- [x] Every task has at least one automated verification command.
- [x] Every must-have maps to focused automated coverage and/or an authorized live gate.
- [x] No three consecutive tasks lack automated feedback.
- [x] No watch-mode flag is used.
- [x] Live trigger preconditions and exact run-ID propagation are explicit.
- [x] Ambiguous maintenance commits fail closed with no retry.
- [x] Known coverage baseline is documented without weakening the threshold.
- [x] `nyquist_compliant: true` and `wave_0_complete: true` are set.

## Validation Audit 2026-08-15

| Task ID | Layer | Gap tested | Behavioral evidence | Command | Status |
|---------|-------|------------|---------------------|---------|--------|
| 260815-ulp-03a | unit | `verify_maintenance_dag.main()` had no executable fail-closed control-flow coverage | One trigger and exact success; failed DagRun; successful DagRun with incomplete audit; timeout; malformed-state uncertainty | `uv run --locked pytest tests/test_h1_runtime.py -q` | green (`26 passed`) |
| 260815-ulp-01d / 02c | feature | DAG checks inspected structure but did not execute task callables | Real Airflow task callables ran in the existing container with controlled connections; exact maintenance order/commit/audit/re-raise and four-table staging acceptance/rejection asserted | `uv run --locked pytest tests/test_dags.py -m airflow -q` | green (`10 passed`) |
| 260815-ulp-01b | integration | Preserve distinct real Trino/Iceberg procedure compatibility coverage | Existing isolated `test_maintenance_procedures` retained; no redundant stateful integration added or rerun during this read-only audit | `uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -q -s` | green (recorded `1 passed`) |
| 260815-ulp-03d | e2e | Completed live proof lacked a repeatable non-mutating pytest gate | Exact receipt IDs queried read-only for successful DagRuns, task map indexes/attempts, DWH audits, and persisted runtime mode | `AIRFLOW_RECEIPT_E2E=1 uv run --locked pytest tests/e2e/test_airflow_run_receipts.py -m "e2e and airflow" -q` | green (`2 passed`) |

Audit totals: 4 gaps found, 4 filled, 0 escalated. Canonical fast suite: `166 passed, 34 deselected`. The E2E command ran with maintenance receipt `maintenance_verify_20260815T222907391492Z_3be4ca723766` and batch receipt `batch_verify_20260815T223250865259Z_6c9d0f4252d6`; it performed no trigger, clear, retry, replay, backfill, or write.

**Approval:** passed — implementation evidence and both authorized one-shot live gates were independently verified on 2026-08-15.
