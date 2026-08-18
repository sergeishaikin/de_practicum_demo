---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 4 EXECUTING - 04-01 through 04-04 complete and summarized; 04-05 (GLD-01) is next. Phase 1 01-07 (DEC-01) remains live and unexecuted.
last_updated: "2026-08-18T00:00:00.000Z"
last_activity: 2026-08-18 -- Executed 04-04 (cycle-complete liveness marker); closed and summarized
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 28
  completed_plans: 21
  percent: 75
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-08-09)

**Core value:** Business-key current state must remain correct and recoverable while the pipeline processes only committed incremental work.
**Current focus:** Phase 4 — Medallion Telemetry and Redundant Work Elimination (executing, 4 of 10 plans)

## Current Position

Phase: 4 (Medallion Telemetry and Redundant Work Elimination) — EXECUTING
Previous: Phase 3 (Staging Source Freshness Gate) — COMPLETE
Plan: 4 of 10 executed (04-01 wave 1, 04-02 wave 2, 04-03 wave 3, 04-04 wave 4); 04-05 is next
Status: EXECUTING. Ten plans across eight waves. Wave 4 landed the harness liveness signal, so wave 5 may now delete the every-cycle-Gold invariant without hanging ci-m5-gates. 04-09 (BENCH-01) is not autonomous and needs authorised mutation of the canonical dwh.
Previous phase: Phase 3 COMPLETE - warehouse-dbt-contract green, fresh PASS / stale ERROR STALE exit exactly 1, 8/8 mutations killed. PR sergeishaikin#1.
Last activity: 2026-08-18 -- Executed 04-04 (cycle-complete liveness marker); closed and summarized

Progress: ████░░░░░░ 40% of Phase 4 (4 of 10 plans executed)

**Open work outside Phase 4:** Phase 1 `01-07-PLAN.md` (DEC-01 rollout decision)
is authorized and still unexecuted. Phase 4 did **not** absorb or supersede it —
Phase 4 was opened by the Rust feasibility investigation, which is not a DEC-01
decision gate. 01-07 must consume the green 01-06 artifacts and reach its own
outcome (open_d3a / open_o2 / no_change). Until it is executed, Phase 1 reads as
partial (13 plans / 12 summaries) and GSD's resume-incomplete-phase invariant
will route to Phase 1 ahead of Phase 4.

## Performance Metrics

**Historical baseline:** M1–S1.2B verified. Current phase has two executed plans; 01-02 failed closed and was rolled back safely.

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. B2 Controlled Rollout | 4 | 12 | planning / evidence closure |
| Phase 01 P01 | 25min | 2 tasks | 5 files |
| Phase 01 P02 | 10min | 2 tasks | 4 files |
| Phase 01 P02C | 30m | 2 tasks | 4 files |
| Phase 02 P01 | 1h 12m | 3 tasks | 30 files |
| Phase 04 P04 | unrecorded | 3 tasks | 3 files |

## Accumulated Context

### Roadmap Evolution

- Phase 2 added: Warehouse Asset-Orchestrated Batch Split. This is Phase 1 of the Airflow orchestration roadmap; Airflow-owned medallion remains an unapproved seed.
- Phase 4 added: Medallion Telemetry and Redundant Work Elimination. Opened after a Rust feasibility investigation found no justified Rust candidate but did expose a metric-identity defect and redundant full-state work.
- Phase 3 added: Staging Source Freshness Gate. Closes the one remaining dbt data-quality dimension. Design approved in `docs/superpowers/specs/2026-08-17-warehouse-source-freshness-design.md`; scope is fixed by that spec.

### Decisions

- B2 canary keeps Gold on legacy until M5 is green.
- Persisted-Silver Gold cutover must keep shadow comparison enabled.
- Phase 2 keeps ingestion manual, uses `core.orders` as the sole scheduling Asset, and records native source DagRun provenance in nullable `ingestion_run_id`.
- Airflow-owned medallion remains a future evaluation seed, not an approved requirement or continuation of Phase 2.
- D-3a and O2 remain conditional, not active work.
- [Phase 01]: Keep the runtime contract at legacy/legacy/0 until a guarded canary is authorized.
- [Phase 01]: Use the installed dbt CLI because `python -m dbt` is unavailable; preserve documented arguments and record the launcher deviation.
- [Phase 01]: Treat all 255 remaining manifests as legitimate LIVE_POST_MIGRATION work and make no data, progress, or outbox change during preflight.
- [Phase 01]: Canary failed closed after UncheckedSQLException/SQLite catalog concurrency and zero successful shadow cycles; restore legacy/legacy/0 before any later plan.
- [Phase 01]: 01-02A must remove the SQLite catalog concurrency root cause; sleeps and blind retries are not sufficient.
- [Phase 01]: 01-02B must preserve all four Spark checkpoints and keep `KAFKA_FAIL_ON_DATA_LOSS=true`; no checkpoint reset is authorized without continuity proof.
- [Phase 01]: 01-02C passed with a fresh non-empty B2 cycle, shadow_comparisons=1, zero mismatches/FF14/in-flight work, and Gold retained on legacy; 01-03 is now the next plan.
- [Phase 01]: 01-02A migrated catalog registrations to PostgreSQL only after SQLite backup/checksum and exact table metadata equivalence; SQLite remains preserved for rollback.
- [Phase 01]: 01-02A concurrency proof passed; two idempotent namespace AlreadyExists 409s are recorded as initialization noise, not lock failures.
- [Phase 01]: 02C PASS: authorize fresh b2/legacy/1 canary only after 02A and 02B-NB green receipts; retain legacy Gold and rollback legacy/legacy/0.
- [Phase 01]: 02C evidence requires a fresh non-empty B2 work metric paired with shadow_comparisons=1, zero mismatches/FF14/inflight, and immutable b2-nb-20260810-01 state.
- [Phase 01]: 01-03 remains STOP / HISTORICAL_EVIDENCE_GAP; 01-03F adds an immutable forward completion ledger without backfilling historical identities.
- [Phase 01]: 01-06 PASS used one bounded higher-version event for an existing key; B2 recorded complete scan/write/snapshot cost, zero mismatches/FF-14/in-flight work, and retained `b2/persisted_silver/1`.
- [Quick 260815-ulp]: Airflow maintenance and batch hardening passed exact one-shot live verification under `b2/persisted_silver/1`; no retry, clear, replay, backfill, or historical-evidence mutation occurred.
- [Phase 2]: Keep ingestion manual, trigger marts validation/publication from the successful `core.orders` Asset event, preserve marts as views, and add source ingestion provenance without renaming `marts.pipeline_runs.run_id`.
- [Phase 4]: `cycle_id IS NULL` is the predicate separating pre-Phase-4 metric rows from Phase-4 rows. Historical rows are never backfilled — an un-instrumented run must not be able to masquerade as an instrumented one.
- [Phase 4]: No new `status` literal is introduced. "The fast path was taken" is expressed by the `shadow_skipped` / `gold_skipped` booleans, because `postgres_exporter.py` hard-codes the status set for SOURCE_UP and `alerts.yml` keys `LakehouseApplicationFailure` on `status="failed"`.
- [Phase 4]: Per-phase metric granularity lives in PostgreSQL only. Prometheus observation is guarded on `phase in (None, "cycle")`; no phase label, no new collector, no new metric name, so every Grafana target and alert expression keeps working unchanged.
- [Phase 4]: `classify_metric_row` returns `"nested"` (not `"b2"`) for `status="failed"` rows, because that row could come from `run_b2` or from `_legacy_silver_cycle`, and asserting an unsupported origin would violate the requirement's own evidential-honesty premise.
- [Phase 4]: 01-07 is NOT superseded by Phase 4. The DEC-01 gate must be executed and its outcome recorded, not declared by inference.
- [Phase 4]: `silver_duration_ms` and `gold_duration_ms` stay populated only on the `cycle` row, keeping today's inclusive meaning. They are never reused for a phase-scoped value, so historical rows stay byte-for-byte interpretable.
- [Phase 4]: `b2 + shadow + gold` is deliberately <= the cycle duration. The residual is the incremental writer's state-load preamble and is attributed to no phase; the subtraction carries a comment so a reader does not read it as an arithmetic bug.
- [Phase 4]: A deployment proves it ran by announcing a completed cycle on stdout, not by leaving a new Gold snapshot. The marker format `cycle-complete cycle_id= gold= shadow= duration_ms=` is fixed for the rest of the phase; `gold=skipped` and `shadow=skipped` are defined but unreachable until 04-05 and 04-06.
- [Phase 4]: No marker is printed for an aborted or early-returning cycle. Absence of the signal is the signal, so a deployment that never completed a cycle cannot pass as one that did.
- [Phase 4]: 04-04's live layer was deliberately not executed locally — no Docker, no stack. The subprocess/pipe wiring between the emit site and `CycleWatcher` is proved by `ci-m5-gates.yml` on the PR; everything either side of the pipe is proved by stackless tests.
- [Phase 4]: The `-m bdd` gate named in 04-03 Task 2 is a plan defect — 23 of those tests also carry `integration`/`airflow` markers and need a live stack the plan is not authorised to start. The executed substitute is `-m "bdd and not integration and not airflow"`. 04-04 or 04-07 should restate it.

### Pending Todos

Historical 01-02B, 01-02B-R, and 01-03 remain immutable STOP results. 01-02B-NB
established the independent epoch `b2-nb-20260810-01`, and 01-02C passed its
guarded B2 canary without claiming historical continuity. 01-03F then proved
durable per-identity completion evidence on one new bounded fixture; no
historical replay or backfill ran. 01-04 passed its pure M5 gate and 01-05
completed the controlled persisted-Silver Gold cutover.

01-06 first preserved its STOP evidence and corrected the Prometheus Counter
query from `lakehouse_correctness` to `lakehouse_correctness_total`. A bounded
remediation then instrumented the B2 scan and committed snapshot, published one
higher-version event for an existing key, and retried the same gate. Ten
consecutive successful rows include one non-empty B2 cycle with complete
physical cost, five green shadow comparisons, zero FF-14 conflicts, and final
in-flight work of zero. 01-07 is authorized but was not executed.

### Blockers/Concerns

Historical per-ID proof remains incomplete for 156 legacy identities and is
accepted as unrecoverable. Future B2 processing is protected by the durable
completion ledger; no historical cleanup, replay, or identity fabrication is
authorized.

- Runtime must remain `b2/persisted_silver/1`; 01-07 must consume the green 01-06 artifacts and must not infer a D-3a/O2 outcome without its own decision gate.

- 01-02 failed closed: Iceberg REST uses `jdbc:sqlite:file:/catalog/iceberg_catalog.db`, and live concurrent access produced `UncheckedSQLException`/unknown failure with zero successful shadow cycles. 01-02A read-only diagnosis is captured, but metadata-preserving migration to a concurrent backend is not yet proven.
- Orders streaming failed closed on unavailable Kafka history: checkpoint offset `218961` versus available offset `157`. The old checkpoint must be preserved; a new epoch requires business-state continuity proof.
- 01-02A is complete. Historical 01-02B and 01-02B-R both stopped fail-closed: the stable Kafka range is 0..40208 (40209 messages), all are absent from Bronze, landing output ends at 218960, and the current checkpoint objects end at 157. Historical continuity cannot be restored. Do not reset old checkpoints or use startingOffsets=latest. Establish a fresh durable new-epoch baseline before 01-02C.

## Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260815-ulp | Harden Airflow maintenance and batch workflows with exact live verification | 2026-08-15 | `2187c5e` | Verified | [260815-ulp-improve-airflow-workflows-resolve-the-pr](./quick/260815-ulp-improve-airflow-workflows-resolve-the-pr/) |
| 260816-dbt | Add a dbt/SQL testing layer: unit tests, cross-model invariant, staging-to-reconciliation integration fixture | 2026-08-16 | `2b91dc1` | Verified | [260816-dbt-sql-testing-layer](./quick/260816-dbt-sql-testing-layer/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Performance | D-3a physical layout tuning | Telemetry-triggered | 2026-08-09 |
| Diagnostics | O2 tracing | Only if O1 insufficient | 2026-08-09 |
| Architecture | Multi-writer support | Accepted current-scale risk | 2026-08-09 |

## Session Continuity

Last session: 2026-08-18
Stopped at: Phase 4 wave 4 complete (04-01 through 04-04), each summarized.
Resume order: (1) execute 01-07 as its own DEC-01 closure — still outstanding,
Phase 1 remains 12/13; (2) return to Phase 4 at 04-05 (GLD-01), which may now delete
the every-cycle-Gold invariant because 04-04 replaced the harness's dependency on it;
(3) stop at 04-09 for the authorised canonical-`dwh` mutation checkpoint.
Note: an external watcher auto-committed with message `1` and switched the checkout
to feat/SQLMesh twice during 04-03. History was rewritten to remove both; verify
branch and HEAD before writing if it recurs.
Resume file: None
