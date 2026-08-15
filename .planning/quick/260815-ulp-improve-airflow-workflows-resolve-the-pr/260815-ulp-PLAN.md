---
phase: quick
plan: 260815-ulp
type: execute
wave: 1
depends_on: []
files_modified:
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
autonomous: true
requirements:
  - QUICK-260815-ULP
must_haves:
  truths:
    - "Each Iceberg target runs the existing optimize, snapshot-expiry, and orphan-file procedures once with retries=0, explicit clean_expired_metadata=false, unchanged retention/recovery settings, and no Trino or catalog migration."
    - "Every mapped maintenance task commits its own ok/noop or failed:<operation> audit row before returning or re-raising, and Airflow runs at most one mapped maintenance instance at a time per DagRun."
    - "The batch DAG admits one active run and blocks core/marts mutation unless all four configured staging tables are non-empty and exactly match their CSV data-row counts."
    - "The maintenance verifier can pass only for one freshly generated run_id with exactly one ok/noop row for each configured target, never from stale, duplicate, missing, extra, or failed rows."
    - "One-shot live maintenance and batch proofs preserve table identity, logical data semantics, b2/persisted_silver/1 runtime state, and historical rollout evidence; an ambiguous maintenance commit is inspected and never blindly retried."
  artifacts:
    - path: "dags/lakehouse_maintenance.py"
      provides: "Compatible, serialized per-table maintenance with durable per-map audit ownership"
      contains: "clean_expired_metadata => false"
    - path: "dags/demo_core_marts_pipeline.py"
      provides: "Single-run batch orchestration and four-table staging validation gate"
      contains: "validate_staging"
    - path: "scripts/verify_maintenance_dag.py"
      provides: "Unique exact-run maintenance audit verifier"
    - path: "tests/test_dags.py"
      provides: "Airflow graph, mapping, concurrency, asset, and retry regression coverage"
    - path: "tests/integration/test_iceberg_trino.py"
      provides: "Real Trino/Iceberg procedure compatibility coverage"
    - path: "docs/TESTING.md"
      provides: "Fail-closed one-shot verification contract"
  key_links:
    - from: "dags/lakehouse_maintenance.py::maintain_table"
      to: "marts.maintenance_runs"
      via: "synchronous PostgreSQL upsert keyed by (run_id, table_name) on both success and failure"
      pattern: "on conflict \\(run_id, table_name\\) do update"
    - from: "dags/lakehouse_maintenance.py::maintain_table"
      to: "Trino Iceberg expire_snapshots"
      via: "one non-retried procedure call using explicit clean_expired_metadata=false"
      pattern: "clean_expired_metadata => false"
    - from: "dags/demo_core_marts_pipeline.py::load_raw_csv_to_stg"
      to: "dags/demo_core_marts_pipeline.py::rebuild_core_and_marts"
      via: "validate_staging dependency that checks all STG_LOADS before rebuild"
      pattern: "chain\\(load_stg, staging_check, rebuild"
    - from: "scripts/verify_maintenance_dag.py::trigger"
      to: "scripts/verify_maintenance_dag.py::audit_rows_for_run"
      via: "the same generated run_id passed to Airflow and parameterized into the exact audit query"
      pattern: "where run_id = %s"
    - from: "scripts/dump_dag_structure.py"
      to: "tests/test_dags.py"
      via: "serialized task and DAG concurrency metadata asserted from the live Airflow DagBag"
---

<objective>
Resolve the known Trino 483/Iceberg REST 1.6.0 snapshot-expiry incompatibility and harden both Airflow workflows without changing data, retention, recovery, catalog, or rollout semantics.

Purpose: Restore safe maintenance, make every table outcome auditable, prevent unsafe concurrency, stop incomplete staging at its boundary, and make live verification exact and fail-closed.
Output: Updated maintenance and batch DAGs, exact-run verifier, focused regression/integration coverage, aligned operational documentation, and one-shot live evidence.
</objective>

<cohesion_note>
The 13-file scope is one cohesive operational change: two existing DAGs implement the required behavior, one existing verifier proves the exact live outcome, focused existing tests protect those contracts, and the five affected docs are aligned with runtime behavior. The plan creates no production module, service, dependency, wrapper, task runner, or validation framework.
</cohesion_note>

<execution_context>
@C:/Users/serge/.codex/get-shit-done/workflows/execute-plan.md
@C:/Users/serge/.codex/get-shit-done/templates/summary.md
</execution_context>

<context>
@AGENTS.md
@.planning/STATE.md
@.planning/quick/260815-ulp-improve-airflow-workflows-resolve-the-pr/260815-ulp-RESEARCH.md
@dags/lakehouse_maintenance.py
@dags/demo_core_marts_pipeline.py
@scripts/dump_dag_structure.py
@scripts/verify_maintenance_dag.py
@tests/test_dags.py
@tests/test_h1_runtime.py
@tests/test_residual_remediation.py
@tests/integration/test_iceberg_trino.py
@README.md
@docs/ARCHITECTURE.md
@docs/CONFIGURATION.md
@docs/DEVELOPMENT.md
@docs/TESTING.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Make mapped Iceberg maintenance compatible, serialized, and self-auditing</name>
  <files>dags/lakehouse_maintenance.py, scripts/dump_dag_structure.py, tests/test_dags.py, tests/test_residual_remediation.py, tests/integration/test_iceberg_trino.py</files>
  <action>
Refactor `lakehouse_maintenance` so each `maintain_table` mapped instance owns the complete lifecycle for one hardcoded `MAINTENANCE_TARGETS` entry: capture its before count, run `optimize`, `expire_snapshots`, and `remove_orphan_files` in the existing order, capture its after count, and synchronously upsert its own `marts.maintenance_runs` row keyed by `(run_id, table_name)`. Pass `{{ run_id }}` into the mapped task and remove the shared `capture_before`/`write_audit` reduce path, because an `all_success` reducer cannot persist sibling outcomes after one map failure.

Keep `RETENTION`, `RETAIN_LAST`, `RECOVERY_HORIZON`, `RECOVERY_SAFETY_MARGIN`, `FILE_SIZE_THRESHOLD`, schedule, `max_active_runs=1`, target tables, operation order, transaction boundaries, and DAG-level `retries=0` unchanged. Change only the expiry argument from `clean_expired_metadata => true` to the explicit documented-compatible `clean_expired_metadata => false`; do not change the Trino image/version, Iceberg REST image/version, JDBC catalog, registrations, warehouse locations, table ownership, or schemas. Do not add a retry loop or retry wrapper around any commit-capable Trino procedure.

Track the current operation with the exact labels `capture_before`, `optimize`, `expire_snapshots`, `remove_orphan_files`, and `capture_after`. On success, write the existing `ok`/`noop` status and return normally. On an exception, perform only a read-only best-effort fresh snapshot count, durably commit `failed:<operation>` with nullable before/after counts through a parameterized PostgreSQL upsert, then re-raise the original maintenance exception so the mapped task and DagRun stay failed. Keep the full exception and Trino query identifier in the mapped task log; never convert a failed maintenance operation into a successful task. Use only local helper functions in the existing DAG module and the existing audit table; do not introduce callbacks, listeners, pools, schemas, dependencies, services, or generic audit frameworks.

Set native Airflow task concurrency on the mapped decorator with `max_active_tis_per_dagrun=1`, leaving global scheduler parallelism unchanged. Extend `dump_dag_structure.py` to expose task-level `max_active_tis_per_dagrun`, then update `test_dags.py` for the single mapped task graph, exact map limit, unchanged DAG run limit/retry/timeout/targets, and existing display metadata. Strengthen `test_residual_remediation.py` to guard the explicit false flag, absence of the incompatible true flag/retry behavior, and failure-status/audit ownership contract. Change the real `test_maintenance_procedures` SQL to pass `clean_expired_metadata => false` explicitly while retaining its snapshot and logical row-count assertions.
  </action>
  <verify>
    <automated>uv run --locked pytest tests/test_residual_remediation.py -q</automated>
    <automated>uv run --locked pytest tests/test_dags.py -m airflow -q</automated>
    <automated>uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -q -s</automated>
  </verify>
  <done>The maintenance DagBag contains one mapped `maintain_table` task limited to one active TI per DagRun; every table instance commits an exact success/failure audit and re-raises operation errors; the real Trino procedure path succeeds with explicit metadata cleanup disabled; all retention, recovery, target, zero-retry, and data contracts remain unchanged.</done>
</task>

<task type="auto">
  <name>Task 2: Serialize the batch DAG and gate core rebuild on exact staging parity</name>
  <files>dags/demo_core_marts_pipeline.py, scripts/dump_dag_structure.py, tests/test_dags.py</files>
  <action>
Add `max_active_runs=1` to `demo_core_marts_pipeline` so two manual runs cannot interleave the shared staging truncate/load and core rebuild. Add a `validate_staging` TaskFlow task after `load_raw_csv_to_stg` and before `rebuild_core_and_marts`, with `inlets=STG_ASSETS` and no outlets. For each of the four fixed `STG_LOADS` entries, count CSV data records with Python's standard `csv` module (open with `newline=""`, consume exactly one header record so quoted multiline fields are parsed correctly), query the corresponding hardcoded staging table with `count(*)`, and require both counts to be greater than zero and exactly equal. Collect/report table, file, CSV count, and staging count for any mismatch, then raise `AirflowException` before any core/marts SQL runs. Do not accept approximate counts, validate only one table, add business rules already owned by later gates, interpolate untrusted identifiers, or create another validation framework/package.

Wire the exact chain as `load_raw_csv_to_stg -> validate_staging -> rebuild_core_and_marts -> check_payment_reconcile -> write_audit`. Preserve the existing load transaction, core/mart SQL, payment threshold, audit behavior, assets, schemas, deduplication, and all business transformations. Update the live DagBag assertions for the new task/dependencies, batch `max_active_runs=1`, four validation inlets/zero outlets, and the unchanged asset counts of every existing task.
  </action>
  <verify>
    <automated>uv run --locked ruff check dags/demo_core_marts_pipeline.py scripts/dump_dag_structure.py tests/test_dags.py</automated>
    <automated>uv run --locked pytest tests/test_dags.py -m airflow -q</automated>
  </verify>
  <done>The batch DagBag admits one active run, exposes the five-task chain with the staging gate in the correct position, and cannot reach core/marts mutation unless each of the four non-empty CSV inputs exactly matches its staging-table row count.</done>
</task>

<task type="auto">
  <name>Task 3: Harden exact-run verification, align docs, and execute one-shot live proofs</name>
  <files>scripts/verify_maintenance_dag.py, tests/test_h1_runtime.py, README.md, docs/ARCHITECTURE.md, docs/CONFIGURATION.md, docs/DEVELOPMENT.md, docs/TESTING.md</files>
  <action>
Replace the verifier's lookback-window matching with one unique, printed run ID generated before trigger (prefix `maintenance_verify_`, UTC timestamp plus collision-resistant suffix). Pass that same ID once via `airflow dags trigger -r`, query `marts.maintenance_runs` only with parameterized `where run_id = %s`, and poll the exact DagRun plus exact audit key. Pass only when there are exactly three rows, each expected table appears exactly once, every status is `ok` or `noop`, there are no missing/extra/duplicate targets, and the exact DagRun is successful. Failed statuses, a failed DagRun, timeout, malformed CLI output, or database/CLI uncertainty must exit non-zero. Remove the time-window success path. Keep this as the existing script using the standard library and installed dependencies; add no wrapper, service, task runner, verification framework, or retry trigger. Add focused tests in `test_h1_runtime.py` for unique run-id propagation and classification rejection of stale-equivalent, missing, duplicate, extra, and failed rows.

Update the README and Airflow/architecture/configuration/testing docs to state: explicit `clean_expired_metadata=false` retains obsolete schema/spec metadata while the existing snapshot/file retention still runs; mapped table operations are scheduler-serialized and self-auditing; failures use `failed:<operation>` and remain failed; the batch chain includes four-table exact non-empty staging parity and one active run; and the verifier uses an exact unique run rather than a time lookback. Remove stale claims that a shared final audit task owns maintenance results. Do not present a catalog/Trino version change or a changed retention/data contract.

After all static and container checks pass, perform the authorized live proof fail-closed. First wait for any active maintenance DagRun to finish and capture a read-only baseline for all three targets: table UUID, warehouse location, current metadata location, current schema/schema ID, partition spec/spec ID, logical row count, snapshot IDs/count, the retention contract, and runtime values `SILVER_MODE=b2`, `GOLD_SOURCE=persisted_silver`, `SHADOW_COMPARE=1`. Do not reset/recreate volumes, clear tasks, edit checkpoints, modify environment/runtime modes, backfill identities, or alter historical 01-02B/01-02B-R/01-03 evidence. Only after this baseline exists, invoke the hardened maintenance verifier once. If trigger creation, a task, or any commit-capable operation has an ambiguous outcome, stop immediately: do not trigger, clear, or retry; record the exact operation/query ID and inspect Airflow task logs, Iceberg REST logs, the authoritative metadata pointer, and snapshot history against the baseline.

On a successful exact run, recapture the same inventory and require unchanged UUID, location, current schema/spec, logical row counts, and `b2/persisted_silver/1`; snapshot IDs/counts may change only as expected from maintenance. Require exact-run task/REST logs to contain none of `remove-schemas`, `Cannot determine whether the commit was successful`, `CommitFailedException`, or generic internal errors. Then capture batch pre-state (all four CSV/staging counts plus existing core/mart counts and reconciliation totals), trigger `demo_core_marts_pipeline` once with its own unique run ID, and require the exact `marts.pipeline_runs` row to be `success`, four-table non-empty parity, and unchanged business counts/aggregates for the unchanged CSV inputs. Record all commands, run IDs, results, and any skipped/failed gate in the quick-task summary; never claim a live check passed unless it ran.
  </action>
  <verify>
    <automated>uv run --locked pytest tests/test_h1_runtime.py -q</automated>
    <automated>uv run --locked ruff check scripts/verify_maintenance_dag.py tests/test_h1_runtime.py</automated>
    <live>uv run --locked python scripts/verify_maintenance_dag.py (exactly once, only after the recorded maintenance pre-state)</live>
    <live>Trigger `demo_core_marts_pipeline` exactly once with a unique run ID after its recorded pre-state; query only that `marts.pipeline_runs.run_id` and compare the four staging counts and business aggregates.</live>
  </verify>
  <done>Docs and tests describe the implemented contracts; the verifier rejects every non-exact/non-success result; the one-shot maintenance and batch runs have exact successful audit evidence; table identity, logical rows, retention/recovery semantics, current runtime mode, and immutable historical evidence remain unchanged, with no ambiguous operation retried.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Airflow mapped task -> Trino/Iceberg REST | A commit-capable maintenance request can fail after its outcome becomes ambiguous. |
| Airflow task -> PostgreSQL audit | Run IDs, table results, and status cross into durable operational evidence. |
| Raw CSV filesystem -> PostgreSQL staging | External file records must exactly match committed staging rows before downstream mutation. |
| Host verifier -> Airflow/PostgreSQL live state | A stale or broad query can falsely certify the wrong DagRun. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-QUICK-01 | Tampering | Trino maintenance calls | mitigate | Keep retries=0, issue one live trigger only after baseline capture, and stop for authoritative metadata inspection after any ambiguous commit. |
| T-QUICK-02 | Repudiation | `marts.maintenance_runs` | mitigate | Each mapped task synchronously upserts `(run_id, table_name)` on success/failure before return/re-raise; verifier requires exact unique rows/statuses. |
| T-QUICK-03 | Tampering | Batch staging/core boundary | mitigate | `max_active_runs=1` plus exact non-empty four-file/table parity blocks interleaved or incomplete staging from reaching core/marts. |
| T-QUICK-04 | Spoofing | SQL identifiers/run IDs | mitigate | Source identifiers only from fixed repository constants and parameterize all run/status/audit values. |
| T-QUICK-05 | Information Disclosure | Task logs/documentation | accept | Existing local-only trust model and environment-provided credentials are unchanged; do not print secrets in new evidence. |
</threat_model>

<complexity_budget>
Expected: modify 13 existing files; create 0 production/test/framework files; add 0 dependencies, services, schemas, persistent state, configuration flags, or public APIs. New code is limited to local DAG/verifier helpers, one TaskFlow validation task, focused assertions, and contract documentation. Reassess before continuing if implementation proposes a new module/framework/service, a catalog/runtime migration, new durable columns/tables, or unrelated pipeline changes.
</complexity_budget>

<source_audit>

| SOURCE | ID | Feature / Requirement | Task | Status | Notes |
|--------|----|-----------------------|------|--------|-------|
| GOAL | QUICK-260815-ULP | Resolve maintenance incompatibility and harden Airflow workflows without semantic drift | 1-3 | COVERED | Code, tests, docs, and live proof included. |
| REQ | - | No ROADMAP requirement IDs apply to this quick task | - | N/A | Quick-task description is the requirement authority. |
| RESEARCH | R-01 | Explicit `clean_expired_metadata=false`; keep Trino 483 and current REST/JDBC catalog | 1 | COVERED | No stateful runtime migration. |
| RESEARCH | R-02 | Preserve retention/recovery/data contracts and maintenance retries=0 | 1, 3 | COVERED | Regression assertions and live inventory comparison. |
| RESEARCH | R-03 | Per-map durable success/failure audit and re-raise | 1 | COVERED | Shared reducer removed. |
| RESEARCH | R-04 | Native per-DagRun mapped-task serialization | 1 | COVERED | `max_active_tis_per_dagrun=1`. |
| RESEARCH | R-05 | Batch `max_active_runs=1` | 2 | COVERED | DagBag asserted. |
| RESEARCH | R-06 | Exact non-empty CSV/staging parity for all four loads | 2, 3 | COVERED | Separate pre-rebuild gate plus live batch proof. |
| RESEARCH | R-07 | Exact unique-run verifier with success-only statuses | 3 | COVERED | No time-window matching. |
| RESEARCH | R-08 | Existing test stack and real compatibility path | 1-3 | COVERED | Fast, DagBag, integration, and live checks. |
| RESEARCH | R-09 | No new package/framework/wrapper/service | 1-3 | COVERED | Standard library and current platform only. |
| RESEARCH | R-10 | One-shot fail-closed live validation; no blind retry | 3 | COVERED | Pre-state and ambiguous-commit stop rule explicit. |
| RESEARCH | R-11 | Keep `b2/persisted_silver/1` and historical evidence immutable | 3 | COVERED | Explicit mutation exclusions and post-state proof. |
| CONTEXT | - | No quick-task CONTEXT.md exists | - | N/A | User constraints are represented directly above. |

</source_audit>

<verification>
Before declaring the quick task complete:

- `uv run --locked ruff check .`
- `uv run --locked black --check .`
- `uv run --locked pytest`
- `uv run --locked ruff check dags --select AIR3 --preview`
- `uv run --locked pytest tests/test_h1_runtime.py`
- `uv run --locked pytest tests/test_dags.py -m airflow`
- `uv run --locked pytest tests/integration/test_iceberg_trino.py::test_maintenance_procedures -m "integration and iceberg and trino" -s`
- `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet`
- Run the documented coverage command and report the known 79.80%-versus-90% baseline failure if unchanged; do not lower the threshold or add unrelated coverage work.
- Confirm the Airflow scheduler, triggerer, DAG processor, and DagBag are healthy before either live trigger.
- Execute exactly one post-baseline maintenance trigger through the hardened verifier and exactly one separately identified batch trigger; retain exact run IDs and pre/post evidence.
- If any maintenance outcome is ambiguous, stop without a second trigger and classify the commit from authoritative metadata before any further maintenance action.
</verification>

<success_criteria>

- All three implementation tasks and all non-baseline verification gates pass.
- Maintenance runs against the existing Trino/catalog state without `remove-schemas`, blind retries, data-semantic changes, or loss of per-table audit evidence.
- Airflow enforces both mapped maintenance serialization and batch single-run serialization.
- Four-table staging parity blocks downstream mutation on empty or mismatched input.
- Exact-run verifier and one-shot live evidence cannot be satisfied by stale or failed audit rows.
- `b2/persisted_silver/1`, table identity/logical data, retention/recovery contracts, checkpoints, volumes, and historical rollout evidence remain unchanged.
</success_criteria>

<output>
After completion, create `.planning/quick/260815-ulp-improve-airflow-workflows-resolve-the-pr/260815-ulp-SUMMARY.md` with exact commands, run IDs, live evidence, and any known baseline failure.
</output>
