# BDD Coverage Inventory

Capability → contract → existing test → Gherkin gap for the whole repository.

This document is the input for deciding **which** `.feature` files to write. It is
not itself a contract: the contracts live in `tests/features/*.feature`, and in the
pytest suites listed below until a feature covers them.

Status: **4 feature files, 30 scenarios (36 cases)** against ~180 pytest tests
across unit / integration / e2e.

| Feature | Tier | Scenarios | Runs |
|---|:--:|:--:|---|
| `silver_business_state.feature` | T1 | 8 | default fast suite, every PR |
| `data_quality_modes.feature` | T1 | 6 (12 cases) | default fast suite, every PR |
| `legacy_cleanup_safety.feature` | T1 | 7 | default fast suite, every PR |
| `airflow_workflow_behavior.feature` | T3 | 9 | dedicated Airflow job, every PR |

---

## 1. Inclusion rule

A capability earns a Gherkin scenario when the rule survives this rewrite:

> Delete every Python function name, class name, mock, env var and SQL fragment
> from the test. Is there still a system rule left?

Concretely — a scenario is justified when **3+** of these hold:

| # | Question |
|---|---|
| 1 | Observable outcome exists (not a return value — a state, a row, an audit) |
| 2 | A data/business rule can be violated |
| 3 | System state transitions |
| 4 | A materially different reject / fail / fallback path exists |
| 5 | A boundary or threshold matters |
| 6 | Failure behavior is part of the contract |
| 7 | Restart / retry / replay semantics exist |
| 8 | More than one component participates |
| 9 | Evidence (audit, metric, receipt, DLQ row) must be left behind |
| 10 | The rule must survive refactoring |

1–2 → keep it as a plain pytest test.

---

## 2. Execution tiers

`airflow_workflow_behavior.feature` is marked `@pytest.mark.bdd` **and**
`@pytest.mark.airflow`, and its `when` steps shell out via
`docker exec de-demo-airflow python -`. `pytest.ini` `addopts` excludes `airflow`,
so it does not run in the default fast suite. It **does** run on every PR:
`ci-pr.yml:123` has a dedicated job that builds the Airflow image, boots
`de-demo-postgres` + `de-demo-airflow`, waits for health, then runs
`pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"`.

So the cost of that pattern is not "never runs" — it is an image build and a live
container per scenario set. If every new feature copies it, the BDD feedback loop
is measured in minutes and gated on Docker. Tier the features instead:

| Tier | Marks | Runs where | Binds to |
|---|---|---|---|
| **T1 — domain** | `bdd`, `domain` | default fast suite (`ci-pr.yml:65`), no stack | pure production callables (`resolve_against_current`, `build_silver`, `collapse_delta`, `run_quality_checks`, `classify_*`, retention parser, rollout matrix) |
| **T2 — stateful** | `bdd`, `integration` | integration gate, local Compose | existing `isolated_lake` / `lake_schema` fixtures |
| **T3 — orchestrated** | `bdd`, `airflow` / `e2e` | dedicated CI job, nightly | DagBag + `docker exec`, e2e harness |

T1 needs **no CI change**: a feature marked only `bdd`/`domain` is already picked
up by the existing `pytest tests` step. Target: T1 is the majority, because those
are the scenarios that keep the contract honest during refactoring.

---

## 3. Capability → Behavior matrix

`✓` = covered by some test. `G` = covered by Gherkin. `—` = behavior not meaningful.
`!` = **gap worth closing**.

| Capability | Happy | Invalid | Failure | Recovery | Idempotency | Evidence |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Batch staging validation | G | G | G | — | — | ✓ |
| Batch core readiness / Asset publication | G | — | G | — | — | G |
| Batch marts quality + provenance | G | — | G | — | — | G |
| Streaming ingestion (Kafka→landing→PG) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Malformed events / DLQ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Offset loss / checkpoint semantics | ✓ | ! | ✓ | ✓ | — | ✓ |
| Event baseline contract (epoch/hash/event_id) | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Iceberg writer (landing→bronze) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Writer state durability | ✓ | ✓ | ✓ | ✓ | — | — |
| **Dedup / business-version resolution** | **G** | **G** | **G** | ✓ | **G** | — |
| Silver B2 incremental | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Gold aggregation | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| **Quality checks (strict vs permissive)** | **G** | **G** | **G** | — | — | **G** |
| Shadow compare | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Gold source cutover / rollout matrix | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Legacy business-version migration | ✓ | ✓ | ✓ | ! | ✓ | ✓ |
| **Legacy outbox reconciliation / cleanup** | **G** | **G** | **G** | — | **G** | ✓ |
| Lakehouse maintenance | G | ✓ | G | ✓ | — | G |
| Maintenance verifier (exact run id) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Retention vs recovery horizon | ✓ | ✓ | ✓ | ✓ | — | — |
| Trino ⇄ PyIceberg interop | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Observability / metrics evidence | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| E2E isolation | ✓ | — | ✓ | — | — | ✓ |
| dbt semantic layer | ✓ | ✓ | — | — | — | ✓ |
| Runtime reproducibility (H1) | ✓ | ✓ | ✓ | — | ✓ | ✓ |

---

## 4. Per-capability inventory

Legend for **Verdict**: `FEATURE` = write Gherkin · `PARTIAL` = write only the
listed scenarios · `KEEP-PYTEST` = do not Gherkin-ify · `DONE` = specified.

### 4.1 Batch warehouse — staging, core, marts

| Field | Value |
|---|---|
| Contract | Staging row counts must equal source CSV counts and be non-empty; core readiness must precede Asset publication; marts provenance must come from the source ingestion DagRun; payment mismatch blocks mart publication |
| Existing | `tests/features/airflow_workflow_behavior.feature` (9 scenarios), `tests/test_dags.py::test_orders_ingestion_contract`, `::test_marts_validation_contract` |
| Gap | Only the fail-closed edges. Missing: a successful end-to-end batch run producing stg→core→marts with a recorded successful run; partial-failure isolation (one mart table fails, others not published) |
| Verdict | `PARTIAL` — add 2 scenarios to the existing feature |

### 4.2 Streaming ingestion

| Field | Value |
|---|---|
| Contract | Kafka `orders` → Parquet landing **and** monotonic upsert into `marts.streaming_orders`; a lower `business_version` must never regress serving state |
| Existing | `tests/test_m5_fitness_functions.py::test_postgres_serving_upsert_is_monotonic_on_business_version`, `tests/e2e/test_r1_streaming_e2e.py` |
| Gap | Whole capability. The monotonicity rule is a textbook BDD contract: state → event → observable invariant |
| Verdict | `FEATURE` → `streaming_ingestion.feature` (T1 for monotonicity, T3 for the e2e path) |

### 4.3 Malformed events & dead-letter

| Field | Value |
|---|---|
| Contract | An unparseable/invalid event never reaches landing or serving; it lands in the DLQ with a `dead_letter_reason`, is counted, and is reconcilable after restart |
| Existing | `tests/e2e/test_r1_streaming_e2e.py::test_r1_malformed_event_dead_letter_reconciliation_and_replay`, `tests/test_residual_remediation.py::test_streaming_job_has_explicit_dead_letter_and_data_loss_contract` |
| Gap | Whole capability, and the strongest `Scenario Outline` candidate in the repo — one outline over `dead_letter_reason` values instead of per-field scenarios |
| Verdict | `FEATURE` → `malformed_event_handling.feature` |

### 4.4 Offset loss / replay

| Field | Value |
|---|---|
| Contract | Data loss must fail loudly, not silently; compose defaults must not enable silent offset reset; a restart from the same checkpoint must not duplicate business effect |
| Existing | `tests/e2e/test_r1_streaming_e2e.py::test_r1_offset_loss_fails_loudly`, `tests/test_residual_remediation.py::test_streaming_compose_defaults_to_loud_offset_loss`, `::test_streaming_checkpoint_path_resolution` |
| Gap | Replay idempotency is asserted only indirectly through the e2e run. No scenario states "reprocessed messages produce no duplicate business rows" |
| Verdict | `FEATURE` → `streaming_replay.feature` |

### 4.5 Event baseline contract

| Field | Value |
|---|---|
| Contract | Canonical payload is sorted compact JSON with a stable hash; every event carries a non-null epoch and unique `event_id`; wrong epoch / hash mismatch / duplicate id are rejected; lineage fields survive landing and bronze |
| Existing | `tests/test_new_baseline_contract.py` (6 tests) |
| Gap | Rejection rules are behavioral and outline-shaped; hash stability and JSON canonicalization are implementation detail |
| Verdict | `PARTIAL` — one `Scenario Outline` over rejection reasons; keep hash/serialization tests as pytest |

### 4.6 Iceberg writer

| Field | Value |
|---|---|
| Contract | Only Spark-committed files are ingested; each append carries a `load-id`; a crash before commit re-appends exactly once; a crash after commit never appends twice; commit conflicts retry; an invalid commit log fails closed |
| Existing | `tests/test_writer.py` (`TestListNewFiles`, `TestCommittedLoadIds`, `TestRecoverPending`, `TestMain`), `tests/integration/test_crash_recovery.py` (both crash directions) |
| Gap | Whole capability. Highest-value remaining BDD target — the contract is exactly "exactly once, observable in snapshots" |
| Verdict | `FEATURE` → `iceberg_writer.feature` + `writer_crash_recovery.feature` (T2, reuse `isolated_lake`) |

### 4.7 Writer state durability

| Field | Value |
|---|---|
| Contract | A failed state replace preserves the previous valid state; state is fsynced before replace |
| Existing | `tests/test_writer.py::TestState` |
| Gap | "Durability across a crash" is behavioral; `fsync`-before-`replace` is mechanism |
| Verdict | `PARTIAL` — one scenario ("a failed state write leaves the last known-good state intact"); keep the fsync test as pytest |

### 4.8 Silver — dedup and business-version resolution — **DONE**

| Field | Value |
|---|---|
| Contract | One row per `order_id`; the **highest `business_version`** wins; transport offset must never decide; equal version + conflicting payload fails before mutation (FF-14); equal version + identical payload is idempotent; a version change crossing a partition boundary still leaves exactly one global current row; a rejected batch is not partially applied |
| Specified by | `tests/features/silver_business_state.feature` (8 scenarios, T1). Steps bind to `resolve_against_current` (imported by `iceberg_medallion.py:37`) and `build_silver`, so the same domain rule is proven on both the incremental and the legacy rebuild path |
| Still pytest | `tests/test_medallion.py::TestBuildSilver` (Arrow null/typing edges, column order), `tests/test_b2_spike.py`, `tests/test_m5_fitness_functions.py::test_ff04_*`/`ff09`/`ff14`, `tests/integration/test_trino_merge_interop.py` — these keep the implementation-level edges the feature deliberately does not restate |
| Verdict | `DONE` — resolved the documentation drift recorded in §6.1 |

### 4.9 Silver B2 incremental path

| Field | Value |
|---|---|
| Contract | Only advancing keys are committed; progress is bounded; the completion ledger survives progress pruning; historical progress is not backfilled; a crash before commit retries, a crash after commit reconciles without a second snapshot; failed processing writes no success receipt |
| Existing | `tests/test_b2_medallion.py` (11 tests), `tests/integration/test_m3_b2_recovery.py` |
| Gap | Recovery and receipt semantics unspecified |
| Verdict | `FEATURE` → `b2_incremental_processing.feature`, or fold the recovery scenarios into the Silver feature |

### 4.10 Gold aggregation

| Field | Value |
|---|---|
| Contract | Aggregates by `event_date`/`country`/`status`; distinct customer counting; empty input yields empty output, not an error; the daily-metrics grain is unique |
| Existing | `tests/test_medallion.py::TestBuildGold`, `tests/integration/test_iceberg_trino.py::test_gold_aggregation_exact_values`, `dbt/tests/gold_daily_metrics_grain_unique.sql` |
| Gap | Grain uniqueness is a real invariant; exact sums fit a `Scenario Outline` with an Examples table |
| Verdict | `FEATURE` → `gold_aggregation.feature` (small, T1) |

### 4.11 Quality checks — strict vs permissive — **DONE**

| Field | Value |
|---|---|
| Contract | A broken data rule is a violation (null order id, null/non-positive amount, null country, unknown status, null event time); a field the batch does not carry is skipped, not failed; in permissive mode violations are evidence only and publication proceeds; in strict mode the cycle aborts before anything is curated, and the failure is recorded |
| Specified by | `tests/features/data_quality_modes.feature` (6 scenarios / 12 cases, T1). Steps bind to `run_quality_checks` for classification and to `run` for the mode behavior, using the same in-memory catalog/metrics doubles as the medallion unit tests |
| Notes | The violation rules are one `Scenario Outline` over seven defects rather than seven scenarios, per §1. Counter names (`order_id_null`, …) stay out of the scenario text — they are an implementation vocabulary, not the contract |
| Still pytest | `tests/test_medallion.py::TestRunQualityChecks` (per-counter naming and Arrow edges), `TestRun` (bronze-missing skip, metric field detail) |
| Verdict | `DONE` — the fail-open/fail-closed pair is now specified on both sides, including proof that no downstream table exists after a strict abort |

### 4.12 Shadow compare & Gold cutover

| Field | Value |
|---|---|
| Contract | Comparison is independent of row order and transport ordering; the Bronze boundary is pinned before B2 runs; a mismatch fails closed **before** any Gold write and records `shadow_failed`; switching `GOLD_SOURCE` never mutates persisted Silver; `persisted_silver` + shadow off is an invalid runtime state |
| Existing | `tests/test_m4_gold.py` (7 tests), `tests/test_m5_fitness_functions.py::test_runtime_rollout_*`, `::test_m5_cutover_gate_*`, `tests/integration/test_m4_gold_cutover.py` |
| Gap | Whole capability. The rollout matrix is a state machine — ideal `Scenario Outline` over the four legal combinations plus the rejected one |
| Verdict | `FEATURE` → `shadow_cutover.feature` (T1 for the matrix, T2 for the cutover run) |

### 4.13 Legacy business-version migration

| Field | Value |
|---|---|
| Contract | Legacy singletons are classified and backfilled to version 1; a second application changes nothing; duplicate/overlapping history fails closed |
| Existing | `tests/test_business_version_migration.py` (4 tests) |
| Gap | Whole capability, plus a **behavior** gap: no rollback semantics — see §6.3. Decide the semantics before writing the scenario |
| Verdict | `FEATURE` → `business_version_migration.feature` (T1), blocked on the rollback decision |

### 4.14 Legacy outbox reconciliation & cleanup — **DONE**

| Field | Value |
|---|---|
| Contract | A legacy batch is eligible for deletion only when its rows are represented in authoritative state; active in-flight progress withholds it even once its rows are migrated; missing authoritative rows withhold it as unsafe; work observed after the migration boundary is **live, not stale** — excluded from cleanup without being reported as a safety failure; the approval fingerprint is order-independent; the gate refuses on a fingerprint mismatch before inspecting any batch |
| Specified by | `tests/features/legacy_cleanup_safety.feature` (7 scenarios, T1). Steps bind to `classify_manifests`, `cleanup_set_digest` and `_pre_delete_gate` |
| Safety property | Every ineligible case asserts the proposed cleanup set is **empty** — the dangerous action cannot happen, not merely that classification reported a problem (DoD §5–6) |
| Still pytest | `tests/test_s1_2_outbox_reconciliation.py`, `tests/test_s1_2_cleanup.py` — per-reason counter names and receipt field detail |
| Verdict | `DONE` — see §6.5 for a naming defect found in the existing tests while writing this |

### 4.15 Lakehouse maintenance

| Field | Value |
|---|---|
| Contract | `optimize` → `expire_snapshots` → `remove_orphan_files` in exactly that order; a failure stops the sequence, is audited per task, and re-raises; expiry is not retried |
| Existing | `tests/features/airflow_workflow_behavior.feature` (2 scenarios), `tests/test_dags.py` (6 tests), `tests/test_residual_remediation.py::test_each_mapped_maintenance_task_owns_failure_audit`, `::test_maintenance_uses_compatible_non_retried_expiry`, `tests/integration/test_iceberg_trino.py::test_maintenance_procedures` |
| Gap | Failures of `optimize` and `remove_orphan_files` are not specified — only `expire_snapshots`. Fail-closed must be proven per stage |
| Verdict | `PARTIAL` — convert the single failure scenario to a `Scenario Outline` over the three operations |

### 4.16 Retention vs recovery horizon

| Field | Value |
|---|---|
| Contract | Snapshot retention must be **strictly greater** than the recovery horizon plus safety margin; equality is unsafe; unparseable durations are rejected |
| Existing | `tests/test_residual_remediation.py` (4 tests) |
| Gap | An architecture invariant that reads as a system guarantee ("expiry never destroys evidence a restarting writer still needs"), not a config test. The boundary case (`retention == horizon` is unsafe) erodes silently |
| Verdict | `FEATURE` → `retention_recovery.feature` (T1, 3 scenarios) |

### 4.17 Maintenance verifier

| Field | Value |
|---|---|
| Contract | Each verification generates a unique run id, triggers exactly once, queries only that exact run id, accepts exactly one success row per target, fails closed on terminal invalid results, times out without re-triggering, and propagates malformed-state uncertainty |
| Existing | `tests/test_h1_runtime.py` (10 tests) |
| Gap | Strong behavioral shape (exactly-once trigger, no retrigger on timeout, fail-closed on ambiguity) buried in a runtime-contract file |
| Verdict | `PARTIAL` — 4 scenarios, folded into the maintenance feature |

### 4.18 Trino ⇄ PyIceberg interop

| Field | Value |
|---|---|
| Contract | A late lower version never regresses Silver; a delta collapses to one row per key; same version + different payload is dropped; `optimize` compacts deletes and restores PyIceberg reads; time travel exposes snapshot history |
| Existing | `tests/integration/test_trino_merge_interop.py` (7 tests), `tests/integration/test_iceberg_trino.py` (7 tests) |
| Gap | Split required. The **domain** rules are now specified by §4.8. The **protocol** rules (position deletes, CoW property acceptance, `remove-schemas` JSON) must stay integration tests |
| Verdict | `PARTIAL` — one scenario ("Iceberg tables stay queryable and consistent after writer commits and maintenance"); rest stays pytest |

### 4.19 Observability / evidence

| Field | Value |
|---|---|
| Contract | Every writer batch and medallion cycle records rows/files/duration/status; a Postgres failure never breaks ingestion; maintenance records before/after snapshot counts |
| Existing | `tests/test_ops.py::TestMetrics` (8 tests), `tests/test_observability.py` (5 tests), `tests/e2e/test_airflow_run_receipts.py` |
| Gap | The **evidence contract** (a committed batch leaves a success row; a failed batch leaves a failure row and no success row) is behavioral. The Prometheus/Grafana config assertions are not |
| Verdict | `PARTIAL` → `observability.feature`, 3 scenarios: success evidence, failure evidence, metrics outage never breaks ingestion |

### 4.20 E2E isolation

| Field | Value |
|---|---|
| Contract | Each run uses its own topic, landing prefix, namespace and Postgres database; the canonical `dwh` database is provably untouched; failures preserve an artifact bundle |
| Existing | `tests/e2e/test_lakehouse_e2e.py`, `tests/e2e/test_airflow_run_receipts.py` |
| Gap | "One test run cannot observe or corrupt another's data" is a genuine contract; per-service credential wiring is not |
| Verdict | `PARTIAL` — 1–2 scenarios only, low priority |

### 4.21 Explicitly out of scope for Gherkin

Do **not** write scenarios for these. They stay as static/config/unit tests.

| Area | Existing tests |
|---|---|
| Image pinning, no `latest` tags, baked Spark jars | `tests/test_h1_runtime.py` (first 5 tests) |
| uv lock / hash / dependency pin parity | `test_python_dependencies_are_locked_and_installed_with_uv`, `test_runtime_dependency_pins_are_shared_at_the_python_arrow_boundary` |
| Compose declarations, healthcheck presence, port exposure | `tests/test_observability.py::test_compose_declares_*`, `tests/test_h1_runtime.py` |
| DagBag import errors, task-id lists, schedule strings, retry counts | `tests/test_dags.py` |
| Prometheus scrape targets, Grafana panel counts | `tests/test_observability.py` |
| dbt adapter pin, docs presence, source declarations | `tests/test_s1_dbt.py` |
| Trino REST protocol mechanics, CoW property acceptance | `tests/integration/test_trino_merge_interop.py` |
| Serialization/hash internals | `tests/test_new_baseline_contract.py::test_canonical_payload_*` |

---

## 5. Backlog, in waves

Executed in waves rather than straight 1→14, so the step vocabulary and fixture
design can be reassessed after the first few T1 features.

### Wave 1 — domain contracts, every PR

| # | Feature file | Tier | Scenarios | Status |
|---|---|:--:|:--:|---|
| 1 | `silver_business_state.feature` | T1 | 8 | **done** |
| 2 | `data_quality_modes.feature` | T1 | 6 (12 cases) | **done** |
| 3 | `legacy_cleanup_safety.feature` | T1 | 7 | **done** |
| 4 | `retention_recovery.feature` | T1 | 3 | next |
| 5 | `business_version_migration.feature` | T1 | ~5 | blocked on §6.3 |
| 6 | `shadow_cutover.feature` (T1 portion) | T1 | ~4 | decide after reassess |
| 7 | `gold_aggregation.feature` | T1 | ~4 | |

**Reassess the inventory after item 4**, before committing to `shadow_cutover`.

### Wave 2 — stateful guarantees

| # | Feature file | Tier | Scenarios |
|---|---|:--:|:--:|
| 8 | `iceberg_writer.feature` | T2 | ~6 |
| 9 | `writer_crash_recovery.feature` | T2 | ~4 |
| 10 | `shadow_cutover.feature` (T2 portion) | T2 | ~3 |

### Wave 3 — orchestrated behavior

| # | Feature file | Tier | Scenarios |
|---|---|:--:|:--:|
| 11 | `malformed_event_handling.feature` | T1+T3 | ~4 (outline) |
| 12 | `streaming_ingestion.feature` | T1+T3 | ~4 |
| 13 | `streaming_replay.feature` | T3 | ~3 |
| 14 | `airflow_workflow_behavior.feature` | T3 | +3 |

**Two standing constraints:**

1. Every step definition must call the same production callable the existing
   pytest test calls. A BDD-only reimplementation of a rule is worse than no
   scenario — it passes while production drifts.
2. Do **not** migrate existing pytest tests into step definitions. The feature
   specifies the durable rule; pytest keeps the edge cases, Arrow/typing
   behavior, internal structures and specific exceptions.

---

## 6. Findings

1. **Documented Silver contract was stale — fixed.** `README.md` and `CLAUDE.md`
   stated that Silver keeps "the row with the highest `kafka_offset`". The
   implementation sorts by `business_version` descending
   (`iceberg/medallion/iceberg_medallion.py:709`) and `collapse_delta` explicitly
   forbids a transport-offset tie-breaker. Both documents now describe the
   business-version rule and point at the executable contract.

2. **BDD execution cost, not absence.** `airflow_workflow_behavior.feature` does
   run on every PR (`ci-pr.yml:123`), but needs an Airflow image build and a live
   container. T1 avoids that entirely and needs no CI change — see §2.

3. **No rollback behavior for business-version migration.** Migration is proven
   idempotent and fail-closed on ambiguity, but nothing specifies the state after
   a partial failure. This is a missing **behavioral decision**, not a missing
   test: choose atomic all-or-nothing vs restartable per-key migration with
   durable progress, then write the scenario. Blocks backlog item 5.

4. **Maintenance fail-closed is proven for one of three operations.** Only
   `expire_snapshots` failure is specified; `optimize` and `remove_orphan_files`
   failures are assumed to behave the same way.

5. **A misleading test name in the legacy outbox suite.**
   `tests/test_s1_2_outbox_reconciliation.py::test_post_migration_snapshot_is_blocked`
   asserts the opposite of its name: `blocked == 0`, `blocked_reasons == {}`, and
   `live_post_migration == 1`. Post-migration work is classified `LIVE_POST_MIGRATION`
   — current work excluded from cleanup, not a safety failure. Anyone reading the
   test list would conclude the system blocks it. The name should say
   "is treated as live work"; the feature now states the rule correctly regardless.

6. **The `iceberg/` coverage gate is currently red, independent of BDD.**
   `pytest tests --cov=iceberg --cov-fail-under=90` reports 80% on this branch
   with or without the new feature. Largest shortfalls:
   `legacy_outbox_reconciliation.py` 57%, `ops.py` 62%,
   `legacy_business_version_migration.py` 66%. Worth a separate fix — adding
   scenarios will not close a 10-point gap.

---

## 7. Definition of BDD Complete (per feature)

1. One primary success scenario.
2. Every materially different rejection/failure path.
3. Every meaningful boundary condition.
4. Retry / recovery / idempotency, if the operation is stateful.
5. Both what changed **and** what must not have changed, for state mutations.
6. For fail-closed paths: proof that downstream did **not** run.
7. Observable evidence (audit row, metric, DLQ record, receipt) where one is promised.
8. No implementation names in the scenario text.
9. Steps bind to production callables, not to BDD-only reimplementations.
10. The scenario does not restate, at the same level, something a pytest test already proves.

Progress is reported per capability, not as a percentage:

```text
Silver business state:   BDD complete
Quality modes:           not specified
Iceberg writer:          not specified
Runtime pinning:         intentionally not BDD
```
