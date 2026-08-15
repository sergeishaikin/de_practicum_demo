# Quick Task: Improve Airflow Workflows - Research

**Researched:** 2026-08-15  
**Domain:** Airflow 3.3 task mapping, Trino/Iceberg REST maintenance compatibility, PostgreSQL batch validation  
**Confidence:** HIGH

## Summary

The maintenance failure is a versioned REST-protocol incompatibility, not a transient catalog or S3 failure. The running `tabulario/iceberg-rest:latest` image is exactly the locally tagged `1.6.0` image (same image ID/digest, created 2024-08-28), while Trino 483 embeds Apache Iceberg 1.11.0. `[VERIFIED: live Docker inspection; CITED: https://raw.githubusercontent.com/trinodb/trino/483/pom.xml]` Apache Iceberg added the REST `remove-schemas` update in 1.8.0. `[CITED: https://github.com/apache/iceberg/releases/tag/apache-iceberg-1.8.0]`

`clean_expired_metadata => true` asks Trino to clean obsolete schemas and partition specs as part of snapshot expiry. `[CITED: https://trino.io/docs/current/connector/iceberg.html#expire-snapshots]` On the persisted catalog, Trino generated `remove-schemas`; Iceberg REST 1.6.0 failed in `MetadataUpdateParser.fromJson` with `Cannot convert metadata update action to json: remove-schemas`. `[VERIFIED: live Iceberg REST and Airflow task logs]` Trino then correctly reported the commit outcome as ambiguous and warned not to retry blindly. `[VERIFIED: live Airflow task logs]`

**Primary recommendation:** Keep Trino 483 and the current persisted REST/JDBC catalog, but make `clean_expired_metadata => false` explicit. This preserves the existing `2h`/`retain_last=5` snapshot-retention and file-cleanup behavior while retaining obsolete schema/spec definitions in table metadata; it changes no rows, current schemas, table ownership, catalog registrations, or warehouse locations. `[CITED: https://trino.io/docs/current/connector/iceberg.html#expire-snapshots; VERIFIED: tests/integration/test_iceberg_trino.py]`

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Schedule/run serialization | Airflow orchestration | Airflow metadata DB | `max_active_runs=1` belongs on each DAG. `[VERIFIED: repository DAGs; CITED: https://airflow.apache.org/docs/apache-airflow/stable/faq.html]` |
| Per-table maintenance serialization | Airflow task scheduler | Trino | Limit mapped `maintain_table` instances explicitly before they submit write procedures. `[VERIFIED: Airflow 3.3.1 runtime API inspection]` |
| Snapshot/file maintenance | Trino Iceberg connector | Iceberg REST catalog + MinIO | Trino owns procedure execution; REST atomically advances the table metadata pointer and MinIO stores metadata/data files. `[VERIFIED: repository configuration; CITED: https://github.com/apache/iceberg/blob/main/format/spec.md#table-metadata]` |
| Maintenance audit | PostgreSQL `marts` | Airflow mapped task | Each table task must durably upsert its own success or failure before returning/raising. `[VERIFIED: current audit schema and failure behavior]` |
| CSV staging validation | Airflow batch DAG | PostgreSQL staging + raw CSV files | A read-only gate after loading and before core rebuild prevents incomplete staging from reaching core/marts. `[VERIFIED: dags/demo_core_marts_pipeline.py]` |

## Project Constraints (from AGENTS.md)

- Preserve distinct Landing/Bronze/Silver/Gold contracts; do not silently change schemas, deduplication, snapshot behavior, or layer ownership. `[VERIFIED: AGENTS.md]`
- Treat Docker, PostgreSQL, MinIO, and Iceberg as stateful; verify checkpoint/offset/snapshot evidence before recovery or cutover actions. `[VERIFIED: AGENTS.md]`
- Do not reset the stack or mutate state during read-only diagnosis. `[VERIFIED: AGENTS.md]`
- Run Python tooling with `uv run --locked`; use explicit live markers only when dependencies are available. `[VERIFIED: AGENTS.md]`
- Required completion checks for Python changes are Ruff, Black, and pytest; DAG changes additionally require AIR3 lint and live DagBag validation. `[VERIFIED: AGENTS.md]`
- Do not add a test framework, task runner, wrapper, or verification layer. `[VERIFIED: AGENTS.md]`

## Current Path and Root Cause

### Current execution path

```text
hourly/manual DagRun (max_active_runs=1)
  -> capture_before (all three tables)
  -> maintain_table.expand(three targets; currently not task-limited)
       -> optimize
       -> expire_snapshots(clean_expired_metadata=true)
       -> remove_orphan_files
       -> return result
  -> write_audit(all mapped results; default all_success)
```

`write_audit` cannot run when any mapped instance fails, so the existing design loses audit rows for both failed and successful sibling tables in that DagRun. `[VERIFIED: dags/lakehouse_maintenance.py]` In the live scheduled run `scheduled__2026-08-15T21:00:00+00:00`, Bronze and Silver mapped instances failed, Gold succeeded, and `write_audit` became `upstream_failed`; the audit table contained no rows for the new run. `[VERIFIED: live Airflow/PostgreSQL inspection]`

### Compatibility chain

1. Compose uses `trinodb/trino:483` and `tabulario/iceberg-rest:latest`. `[VERIFIED: docker-compose.extended.yml and live containers]`
2. The live REST image digest `sha256:3b7d31...ce472` is identical for local tags `latest` and `1.6.0`. `[VERIFIED: live Docker image inspection]`
3. Trino 483 declares `dep.iceberg.version=1.11.0`. `[CITED: https://raw.githubusercontent.com/trinodb/trino/483/pom.xml]`
4. `remove-schemas` entered the Iceberg REST OpenAPI in the Iceberg 1.8.0 release. `[CITED: https://github.com/apache/iceberg/releases/tag/apache-iceberg-1.8.0; CITED: https://github.com/apache/iceberg/pull/12022]`
5. The live server throws from request parsing, before the catalog handler can apply the table update. `[VERIFIED: live Iceberg REST stack trace]` This explains why the specific failing expire request was not applied, although the client must still treat a generic failed commit as ambiguous. `[VERIFIED: live Trino error text and server stack trace]`

### Why only some table tasks appeared successful

The newer update is emitted only when expired history leaves obsolete schema/spec metadata to remove; a table with no removable metadata need not include that update. `[CITED: https://trino.io/docs/current/connector/iceberg.html#expire-snapshots]` Therefore mixed mapped outcomes are compatible with one deterministic protocol mismatch and are not evidence of a transient service fault. `[VERIFIED: live per-map task states and REST logs]`

## Standard Stack

No new packages, services, or executors are required. `[VERIFIED: repository dependency and runtime inspection]`

| Component | Version | Purpose | Direction |
|---|---:|---|---|
| Apache Airflow | 3.3.1 | DAG scheduling, mapping, run/task limits | Keep; use native operator limits. `[VERIFIED: live runtime]` |
| Trino | 483 (Iceberg 1.11.0) | Iceberg maintenance procedures | Keep pinned. `[VERIFIED: live runtime; CITED: https://raw.githubusercontent.com/trinodb/trino/483/pom.xml]` |
| Iceberg REST image | 1.6.0 digest currently referenced as `latest` | Persisted JDBC catalog front end | Keep for this bounded fix; do not migrate registrations. `[VERIFIED: live Docker inspection]` |
| PostgreSQL | 15.18 live | DWH and operational audit | Reuse `marts.maintenance_runs`. `[VERIFIED: live runtime]` |
| pytest | 8.4.2 locked | Existing tests | Reuse; no new framework. `[VERIFIED: uv.lock]` |

## Remedy Comparison

| Remedy | Safety and compatibility | Decision |
|---|---|---|
| Explicit `clean_expired_metadata => false` | Uses Trino's documented default-compatible path; the existing real integration test already succeeds with metadata cleanup omitted/default false. Snapshot retention, `retain_last`, expired data cleanup, and subsequent orphan cleanup remain active. `[VERIFIED: tests/integration/test_iceberg_trino.py; CITED: https://trino.io/docs/current/connector/iceberg.html#expire-snapshots]` | **Use.** Smallest reversible code change. |
| Upgrade REST image to Iceberg >=1.8 | Would add `remove-schemas` support, but changes a stateful catalog server image and the H1-pinned runtime; it requires full image, JDBC registration, S3 FileIO, and rollback equivalence verification. `[CITED: https://github.com/apache/iceberg/releases/tag/apache-iceberg-1.8.0; VERIFIED: PROJECT.md and prior 01-02A evidence]` | Reject for this quick task. |
| Downgrade Trino | Avoids the new client update but changes the verified Trino runtime and potentially other connector behavior. `[VERIFIED: docs/runtime/H1-reproducible-runtime.md]` | Reject. |
| Reimplement expiry through direct REST/JDBC/PyIceberg calls | Duplicates retention/file-deletion/atomic-commit logic and creates a second maintenance authority. `[CITED: https://github.com/apache/iceberg/blob/main/format/spec.md#snapshot-retention-policy]` | Reject. |

## Recommended Architecture Patterns

### 1. Each mapped task owns its durable audit row

Move before-count capture into `maintain_table`, track the current operation, and upsert the existing `(run_id, table_name)` row from that mapped task on both success and handled failure. `[VERIFIED: current mapping and audit primary key]` Re-raise the original exception after the failure upsert so the mapped task and DagRun remain failed. `[CITED: https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html#dag-run-status]`

Use existing columns only:

- `ok` / `noop` for success. `[VERIFIED: current audit contract]`
- `failed:capture_before`, `failed:optimize`, `failed:expire_snapshots`, `failed:remove_orphan_files`, or `failed:capture_after` for failure. `[RECOMMENDED: minimal operational audit design]`
- Keep the full exception and Trino query ID in the mapped task log; Airflow gives each mapped instance its own log path. `[CITED: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/logging-tasks.html]`

Do not use `on_failure_callback` for the durable audit. Callback errors are written outside the normal task log and callbacks run only for worker-driven state changes. `[CITED: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/callbacks.html]`

```python
# Pattern, adapted to existing helpers; no new abstraction or schema.
operation = "capture_before"
before_count = None
try:
    before_count = _snapshot_count(conn, schema, table)
    for operation, statement in _maintenance_statements(schema, table):
        _execute_once(conn, statement)  # retries remain 0
    operation = "capture_after"
    after_count = _snapshot_count(conn, schema, table)
    _upsert_audit(run_id, full_name, before_count, after_count, status)
except Exception:
    after_count = _best_effort_fresh_snapshot_count(schema, table)
    _upsert_audit(
        run_id, full_name, before_count, after_count, f"failed:{operation}"
    )
    raise
```

### 2. Serialize the mapped maintenance instances explicitly

Set `@task(..., max_active_tis_per_dagrun=1)` on `maintain_table`. Airflow 3.3.1's installed `BaseOperator` accepts this parameter. `[VERIFIED: live runtime API signature]` Combined with existing DAG `max_active_runs=1`, this yields one maintenance procedure chain at a time without Celery/Kubernetes, a new pool, or global scheduler changes. `[VERIFIED: dags/lakehouse_maintenance.py; CITED: https://airflow.apache.org/docs/apache-airflow/stable/faq.html]`

### 3. Make the batch DAG single-run and gate staging explicitly

Add `max_active_runs=1` to `demo_core_marts_pipeline`; without it, two manual runs can interleave `TRUNCATE`, `COPY`, and core rebuild against the same tables. `[VERIFIED: dags/demo_core_marts_pipeline.py]`

Add an inlet-only `validate_staging` task between load and rebuild:

```text
load_raw_csv_to_stg
  -> validate_staging
  -> rebuild_core_and_marts
  -> check_payment_reconcile
  -> write_audit
```

For all four `STG_LOADS`, compare PostgreSQL `count(*)` with the corresponding CSV data-row count and require both to be greater than zero. `[RECOMMENDED: exact boundary validation]` Use Python's standard `csv` module so quoted records are counted correctly, parameterize values, and continue using only the hardcoded table identifiers already present in `STG_LOADS`. `[RECOMMENDED: standard-library implementation; VERIFIED: hardcoded STG_LOADS]` This task reads staging and therefore has `inlets=STG_ASSETS`, but emits no outlet/asset event. `[VERIFIED: existing real Asset model; RECOMMENDED: no fake asset]`

The separate gate intentionally leaves the freshly loaded staging transaction committed if validation fails but prevents any core/marts mutation. `[RECOMMENDED: fail-closed staging boundary]` Do not alter the existing payment reconciliation or final business audit. `[VERIFIED: existing batch contracts]`

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| REST compatibility negotiation | Custom REST payload filter/proxy | Explicit documented `clean_expired_metadata => false` | No new service and no change to atomic commit ownership. `[CITED: https://trino.io/docs/current/connector/iceberg.html#expire-snapshots]` |
| Mapped task throttling | Sleeps, locks, or a custom queue | `max_active_tis_per_dagrun=1` | Scheduler-enforced and visible. `[VERIFIED: Airflow 3.3.1 runtime API]` |
| Failure audit callback framework | Global callbacks/listeners | Local mapped-task upsert then re-raise | Audit and failure share the task execution context. `[CITED: https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/callbacks.html]` |
| CSV validation framework | New data-quality package | `csv` + SQL counts + `AirflowException` | Four fixed files/tables need one exact gate. `[VERIFIED: STG_LOADS]` |
| Retry wrapper | Retry on generic Trino commit errors | One attempt, inspect authoritative state | Trino explicitly warns that retrying an already successful operation can duplicate or unintentionally modify data. `[VERIFIED: live Trino error]` |

## Common Pitfalls

### Stale audit rows produce a false E2E pass

The current verifier selects all rows in a 20-minute window, does not filter by the triggered run ID, and considers table presence sufficient even if a status is failed. `[VERIFIED: scripts/verify_maintenance_dag.py]` Generate a unique run ID with `airflow dags trigger -r <id>`, query exactly `where run_id = %s`, require exactly the three target rows, and accept only `ok`/`noop`. `[VERIFIED: live Airflow 3.3.1 CLI help; RECOMMENDED: exact-run verification]`

### A failure audit that swallows the task exception makes the Dag green

If `maintain_table` catches and returns a failed result, the mapped leaf can succeed despite maintenance failure. `[CITED: https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html#dag-run-status]` Upsert, then re-raise. `[RECOMMENDED]`

### A shared reduce task still cannot consume failed map results

The current reduce task is `upstream_failed` when any map fails. `[VERIFIED: live Airflow task states]` Do not move only the failure formatting into `write_audit`; move persistence into each map instance. `[RECOMMENDED]`

### Retrying after an ambiguous commit

Never automatically retry `optimize`, `expire_snapshots`, or orphan cleanup after a generic catalog/transport failure. `[VERIFIED: live Trino warning]` Record the Trino query ID and operation, then inspect the REST server log and the table's authoritative metadata pointer/snapshot state before any later manual run. `[RECOMMENDED: persisted-state safety]`

### Treating `clean_expired_metadata=false` as disabling snapshot expiry

It only disables cleanup of obsolete schema/partition-spec metadata; the documented snapshot retention procedure still expires snapshots and related files according to `retention_threshold`/`retain_last`. `[CITED: https://trino.io/docs/current/connector/iceberg.html#expire-snapshots]`

### Weak staging validation

Checking only `stg.orders` misses missing dimension/payment/item inputs. `[VERIFIED: four entries in STG_LOADS]` Validate all four tables against their own source files before rebuilding core. `[RECOMMENDED]`

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 8.4.2; Airflow DagBag in live Airflow 3.3.1 container. `[VERIFIED: uv.lock and tests/test_dags.py]` |
| Config | `pytest.ini`; `airflow`, `integration`, `iceberg`, `trino`, and `e2e` are explicit live markers. `[VERIFIED: pytest.ini]` |
| Quick run | `uv run --locked pytest tests/test_residual_remediation.py` `[VERIFIED: repository contract]` |
| DAG run | `uv run --locked pytest tests/test_dags.py -m airflow` `[VERIFIED: AGENTS.md]` |
| Full fast suite | `uv run --locked pytest` `[VERIFIED: AGENTS.md]` |

### Required test changes

| Behavior | Test | Command |
|---|---|---|
| Maintenance uses explicit compatible metadata-cleanup flag and no retry | Add focused source/helper assertions in existing tests. `[RECOMMENDED]` | `uv run --locked pytest tests/test_residual_remediation.py` |
| Mapped task is limited to one active TI per DagRun | Extend `dump_dag_structure.py` with task `max_active_tis_per_dagrun`; assert value `1`. `[RECOMMENDED]` | `uv run --locked pytest tests/test_dags.py -m airflow` |
| Each map owns audit and no reduce task masks failures | Update expected task graph and verify exact tasks/dependencies. `[RECOMMENDED]` | same |
| Batch has `max_active_runs=1` and a real staging gate | Assert DAG limit, `validate_staging` dependency, and four inlets/zero outlets. `[RECOMMENDED]` | same |
| Compatible Trino procedure path remains real | Change integration SQL to explicit `clean_expired_metadata => false`; retain row-count and snapshot assertions. `[RECOMMENDED]` | `uv run --locked pytest tests/integration/test_iceberg_trino.py -m "integration and iceberg and trino" -s` |
| Exact-run maintenance verifier rejects missing/failed rows | Unit-test extracted result classification if kept pure, then run the script once live. `[RECOMMENDED]` | `uv run --locked python scripts/verify_maintenance_dag.py` |

### Completion gate

Run the repository-required commands: `[VERIFIED: AGENTS.md]`

```bash
uv run --locked ruff check .
uv run --locked black --check .
uv run --locked pytest
uv run --locked ruff check dags --select AIR3 --preview
uv run --locked pytest tests/test_h1_runtime.py
uv run --locked pytest tests/test_dags.py -m airflow
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet
```

The existing coverage command has a documented baseline failure at 79.80% against 90%; report it if run and do not lower the threshold. `[VERIFIED: AGENTS.md]`

### One-shot live persisted-catalog proof

1. Wait for any active maintenance DagRun to finish; do not clear or rerun its failed tasks. `[RECOMMENDED: no ambiguous replay]`
2. Capture, for all three tables, table UUID, location, current schema/spec, row count, snapshot IDs/count, and current metadata location; also capture `SILVER_MODE=b2`, `GOLD_SOURCE=persisted_silver`, `SHADOW_COMPARE=1` and the unchanged retention contract. `[VERIFIED: STATE.md current contract; RECOMMENDED: evidence baseline]`
3. Trigger **once** with a unique ID such as `maintenance_verify_<UTC timestamp>` using `airflow dags trigger -r`. `[VERIFIED: live Airflow CLI help]`
4. Poll the exact DagRun and exact `marts.maintenance_runs.run_id`; require three rows, statuses only `ok`/`noop`, and a successful DagRun. `[RECOMMENDED: exact-run proof]`
5. Re-capture the catalog inventory. Require identical UUID/location/current schema/spec and identical logical row counts; snapshot IDs/counts may change because maintenance is designed to commit/expire snapshots. `[CITED: https://github.com/apache/iceberg/blob/main/format/spec.md#snapshots]`
6. Search the exact-run task logs and REST logs for `remove-schemas`, `Cannot determine whether the commit was successful`, `CommitFailedException`, and generic internal errors; require none. `[RECOMMENDED: regression evidence]`
7. If the single run fails after a commit-capable operation, stop. Record operation/query ID, compare the metadata pointer and snapshot history with the baseline, and classify committed/not committed before authorizing any second trigger or orphan cleanup. `[VERIFIED: live Trino warning; RECOMMENDED: fail-closed verification]`

For the batch DAG, use a separate unique run ID once. Capture pre/post staging/core/mart counts and reconciliation totals, require the exact `marts.pipeline_runs` row to be `success`, and require business counts/aggregates to remain equal for the unchanged CSV inputs. `[VERIFIED: current batch audit and SQL contracts; RECOMMENDED: batch E2E]`

## Environment Availability

| Dependency | Available | Version/state | Fallback |
|---|---|---|---|
| Docker | yes | 29.5.3; full stack running. `[VERIFIED: live runtime]` | none needed |
| Airflow | yes | 3.3.1, LocalExecutor. `[VERIFIED: live runtime and compose]` | none needed |
| Trino | yes | 483, healthy. `[VERIFIED: live runtime]` | none needed |
| Iceberg REST | yes | effective 1.6.0 image digest, healthy. `[VERIFIED: live runtime]` | explicit metadata-cleanup false |
| PostgreSQL | yes | 15.18, healthy. `[VERIFIED: live runtime]` | none needed |
| `uv` | yes | 0.10.7. `[VERIFIED: live host runtime]` | none needed |

No missing blocking dependency was found. `[VERIFIED: live environment audit]`

## Security Domain

| ASVS Category | Applies | Control |
|---|---|---|
| V2 Authentication | no change | Existing local-only Airflow/Trino trust model remains unchanged. `[VERIFIED: compose/docs]` |
| V3 Session Management | no | No browser/session change. `[VERIFIED: scope]` |
| V4 Access Control | no change | Do not change catalog principals or table ownership. `[VERIFIED: task constraint]` |
| V5 Input Validation | yes | Keep SQL identifiers sourced only from hardcoded `MAINTENANCE_TARGETS`/`STG_LOADS`; parameterize audit values/run IDs and validate CSV/table counts. `[VERIFIED: repository patterns; RECOMMENDED]` |
| V6 Cryptography | no | No cryptographic behavior. `[VERIFIED: scope]` |

Primary threat is integrity loss from replaying an ambiguously committed maintenance operation (STRIDE: Tampering). Mitigate with zero automatic retries, exact run IDs, authoritative metadata inspection, and fail-closed verification. `[VERIFIED: live Trino warning; RECOMMENDED]`

## Assumptions Log

| # | Claim | Risk if wrong |
|---|---|---|
| A1 | `[ASSUMED]` “Staging validation” means exact non-empty raw-CSV-to-staging row parity for all four configured loads, without adding business rules. | If the desired gate includes additional domain constraints, the planner must add them explicitly; do not invent them during implementation. |

## Open Questions

1. **Does staging validation require rules beyond exact row parity/non-empty inputs?**
   - What is known: Existing `db/demo_sql/05_quality_scorecard.sql` treats non-empty staging as the staging-level quality check, while later tasks cover payment reconciliation, duplicate grain, null keys, and mart reconciliation. `[VERIFIED: repository SQL and DAG]`
   - Recommendation: Keep this quick task to four-table parity/non-empty validation and preserve later gates unchanged. `[RECOMMENDED]`

## Sources

### Primary (HIGH confidence)

- [Trino 483 Iceberg connector documentation](https://trino.io/docs/current/connector/iceberg.html#expire-snapshots) — `expire_snapshots`, `retain_last`, and `clean_expired_metadata`. `[CITED]`
- [Trino 483 root POM](https://raw.githubusercontent.com/trinodb/trino/483/pom.xml) — Iceberg dependency 1.11.0. `[CITED]`
- [Apache Iceberg 1.8.0 release](https://github.com/apache/iceberg/releases/tag/apache-iceberg-1.8.0) and [PR #12022](https://github.com/apache/iceberg/pull/12022) — REST `remove-schemas` introduction. `[CITED]`
- [Apache Iceberg table specification](https://github.com/apache/iceberg/blob/main/format/spec.md) — atomic metadata commits and snapshot retention. `[CITED]`
- [Airflow concurrency guidance](https://airflow.apache.org/docs/apache-airflow/stable/faq.html), [DagRun status](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html), [mapped task logging](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/logging-tasks.html), and [callback caveats](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/callbacks.html). `[CITED]`
- Repository files, live Docker image identity, live Airflow task states/logs, live REST stack traces, and live PostgreSQL audit rows. `[VERIFIED: codebase and runtime inspection]`

## Metadata

**Confidence breakdown:**

- Root cause: HIGH — exact client/server versions plus reproducible server parser stack trace. `[VERIFIED]`
- Remedy: HIGH — documented flag semantics and existing passing integration path with default false. `[VERIFIED/CITED]`
- Audit/concurrency design: HIGH — derived from observed Airflow failure propagation and installed operator API. `[VERIFIED/CITED]`
- Staging validation scope: MEDIUM — implementation shape is grounded, but the requested validation depth is not otherwise specified. `[ASSUMED]`

**Research date:** 2026-08-15  
**Valid until:** 2026-08-22 (runtime compatibility evidence is version-sensitive)
