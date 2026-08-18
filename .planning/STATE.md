---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 4 PLANNED (10 plans, 8 waves); execution not started
last_updated: "2026-08-17T12:00:00.000Z"
last_activity: 2026-08-18 -- Phase 4 planned and plan-checked; 10 plans in 8 waves
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 14
  completed_plans: 13
  percent: 50
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-08-09)

**Core value:** Business-key current state must remain correct and recoverable while the pipeline processes only committed incremental work.
**Current focus:** Phase 3 — Staging Source Freshness Gate (all 4 waves executed)

## Current Position

Phase: 4 (Medallion Telemetry and Redundant Work Elimination) — PLANNED
Previous: Phase 3 (Staging Source Freshness Gate) — COMPLETE
Plan: 4 of 4 complete
Status: COMPLETE. warehouse-dbt-contract green: fresh batch PASS, backdated batch ERROR STALE exit exactly 1, 8/8 mutations killed. Thresholds remain provisional and unmeasured by decision. PR sergeishaikin#1.
Last activity: 2026-08-17 -- Phase 3 wave 4 (03-04) complete

Progress: ▓▓▓▓▓▓▓▓▓▓ 100% of Phase 3 (4 of 4 plans executed)

## Performance Metrics

**Historical baseline:** M1–S1.2B verified. Current phase has two executed plans; 01-02 failed closed and was rolled back safely.

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. B2 Controlled Rollout | 4 | 12 | planning / evidence closure |
| Phase 01 P01 | 25min | 2 tasks | 5 files |
| Phase 01 P02 | 10min | 2 tasks | 4 files |
| Phase 01 P02C | 30m | 2 tasks | 4 files |
| Phase 02 P01 | 1h 12m | 3 tasks | 30 files |

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

Last session: 2026-08-16T11:14:47.418Z
Stopped at: 01-06 PASS; 01-07 authorized but not executed
Resume file: None
