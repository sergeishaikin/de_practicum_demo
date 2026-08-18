# Roadmap: Incremental Lakehouse Demo

## Milestones

- ✓ **Architecture and remediation baseline** — M1–M5, R1/R2, O1, S1, S1.1,
  H1, S1.2A, S1.2A.1, and S1.2B completed and verified at `89953fe`.

- 🚧 **B2 Controlled Rollout** — execute the accepted B2 architecture under
  controlled canary, evidence gate, cutover, and telemetry observation.

- **Airflow Orchestration Boundaries** — split the existing warehouse batch
  workflow at a real Asset publication boundary without changing storage,
  business, streaming, maintenance, or medallion ownership semantics.

## Phases

### Phase 1: B2 Controlled Rollout

**Goal**: Drain legitimate post-migration B2 work safely, prove M5 cutover
conditions, observe real B2 cost, and make an evidence-based D-3a/O2 decision.

**Depends on**: S1.2B verified cleanup at `89953fe`.
**Requirements**: [CAN-01, CAN-02, CAN-03, CUT-01, CUT-02, TEL-01, DEC-01]
**Plans**: 13 plans, including fail-closed runtime gap closure, a deliberate new-epoch baseline, and forward-only completion evidence after historical recovery STOP.

**Wave 1**

- [x] 01-01-PLAN.md — Canary preflight and frozen state verification.

**Wave 2** *(executed and failed closed)*

- [x] 01-02-PLAN.md — First controlled B2 canary; restored legacy/legacy/0 after a recovery anomaly.

**Wave 3** *(completed)*

- [x] 01-02A-PLAN.md — Close Iceberg REST catalog concurrency and SQLite lock failures with metadata-preserving PostgreSQL migration.

**Wave 4** *(blocked on 01-02A)*

- [x] 01-02B-PLAN.md — Reconcile Kafka checkpoint offset loss without resetting history.

**Wave 5** *(terminal STOP after historical 01-02B)*

- [x] 01-02B-R-PLAN.md — Read-only bounded recovery feasibility; STOP / RECOVERY_NOT_PROVEN because canonical source and epoch-safe identity are unavailable.

**Wave 6** *(blocked on 01-02B-R STOP; new baseline required)*

- [x] 01-02B-NB-PLAN.md — Establish a durable, explicit new B2 baseline without claiming historical recovery.

**Wave 7** *(blocked on 01-02B-NB readiness gate)*

- [x] 01-02C-PLAN.md — Repeat the guarded B2 canary and require fresh shadow evidence.

**Wave 8** *(blocked on 01-02C; ended STOP)*

- [ ] 01-03-PLAN.md — Drain and verify the 255 legitimate post-migration manifests.

**Wave 9** *(forward-only remediation after the historical STOP)*

- [x] 01-03F-PLAN.md — Add durable per-manifest completion evidence for future B2 processing; PASS / ready_for_01_04=true.

- [ ] 01-04-PLAN.md — Collect and evaluate M5 cutover evidence.

**Wave 10** *(blocked on Wave 9 completion)*

- [ ] 01-05-PLAN.md — Switch Gold to persisted Silver only after a green M5 gate.

**Wave 11** *(blocked on Wave 10 completion)*

- [x] 01-06-PLAN.md — Collect a representative O1 telemetry window; PASS after bounded instrumentation/workload remediation.

**Wave 12** *(blocked on Wave 11 completion)*

- [ ] 01-07-PLAN.md — Decide D-3a, O2, or no-change and record the rollout result.

## Conditional and Backlog Work

- **D-3a**: Open only if telemetry shows material scan/write amplification.
- **O2**: Open only if O1 diagnostics are insufficient.
- **F-305**: `marts` DDL ownership cleanup.
- **F-306**: Remove runtime `sys.path` mutation.
- **F-709**: Decide whether the legacy PostgreSQL serving path remains needed.
- **F-308**: Separate writer and medallion image/source ownership.
- Multi-writer support remains deferred.

## Progress

Forward remediation: `01-03` remains STOP / HISTORICAL_EVIDENCE_GAP;
`01-03F` is the required bounded forward-only completion-ledger plan before
`01-04` may execute. Historical 156 identities are not backfilled.

Current gate state: `01-03F = PASS`, `ready_for_01_04 = true`.

M5 gate state: `01-04 = PASS`, `ready_for_01_05 = true`; it authorized the
controlled persisted-Silver cutover in 01-05.

Cutover state: `01-05 = CUTOVER_PASS`, `ready_for_01_06 = true`; live runtime
is `b2/persisted_silver/1`. Do not execute 01-06 until the 01-05 receipt is
present and validated.

Telemetry state: `01-06 = PASS`, `ready_for_01_07 = true`. The representative
window contains ten successful rows and one non-empty B2 cycle with complete
planned/added/removed byte and file measures, one snapshot, zero shadow/FF-14
failures, and no in-flight work. 01-07 is the next plan and was not executed.

**Execution Order:** Phase 1 → 01-01 → 01-02 → 01-02A → historical 01-02B STOP → 01-02B-R STOP → 01-02B-NB → 01-02C → 01-03 → 01-04 → 01-05 → 01-06 → 01-07 → Phase 2

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. B2 Controlled Rollout | Current | 8/12 | In Progress|  |
| 2. Warehouse Asset-Orchestrated Batch Split | Airflow Orchestration Boundaries | 1/1 | Complete   | 2026-08-16 |
| 3. Staging Source Freshness Gate | Airflow Orchestration Boundaries | 4/4 | Complete   | 2026-08-17 |

Historical milestones are intentionally summarized above rather than
replayed as unfinished GSD phases.

### Phase 2: Warehouse Asset-Orchestrated Batch Split

**Goal:** Replace the combined manual warehouse DAG with a manual ingestion
DAG and an Asset-triggered marts validation/publication DAG while preserving
the current SQL, quality, audit, and storage semantics.

**Requirements**: [ORCH-01, ORCH-02, ORCH-03, ORCH-04, ORCH-05, ORCH-06, ORCH-07, ORCH-08]
**Depends on:** Phase 1 reaching its terminal rollout decision; Quick Task
260815-ulp verified Airflow 3.3.1 runtime and workflow baseline.
**Plans:** 1/1 plans complete
Plans:

- [x] 02-01-PLAN.md — Split warehouse batch orchestration at the core Asset boundary (completed 2026-08-16)

**Scope contract:**

- `warehouse_orders_ingestion` remains manual and owns staging load,
  exact staging parity, the unchanged `10_rebuild_core.sql` transaction,
  read-only core readiness counts, and final core Asset publication.

- `warehouse_marts_validation` is triggered by the successfully published
  `core.orders` Asset and owns marts validation, payment reconciliation,
  mart Asset publication, and the existing idempotent pipeline audit.

- `marts.pipeline_runs.run_id` remains the downstream DagRun primary key;
  nullable indexed `ingestion_run_id` records Asset-event provenance.

- Marts remain views. Maintenance, medallion, streaming, recovery,
  checkpoints, and Bronze/Silver/Gold publication remain unchanged.

### Phase 3: Staging Source Freshness Gate

**Goal:** Make staging load-recency an explicit, fail-closed prerequisite to mart
certification. Add `loaded_at timestamptz NOT NULL DEFAULT now()` to the four
`stg.*` tables, declare dbt source freshness with `loaded_at_field: loaded_at`,
and enforce it as a distinct task at the consumption boundary in
`warehouse_marts_validation`, before the Cosmos dbt build.

**Guarantee (deliberately narrow):** prevent downstream certification from
consuming staging whose most recent successful load is outside the permitted
age. This is **not** missing-batch detection — the timestamp is written by the
staging load itself and the marts DAG is Asset-triggered by the same pipeline,
so if ingestion never runs the gate never evaluates.

**Approved design:** `docs/superpowers/specs/2026-08-17-warehouse-source-freshness-design.md`
— implement as specified; do not redesign unless implementation proves it
impossible.

**Requirements**: [R1, R1c, R2, R2b, R2c, R2d, R3, R6, R7] — new work; and
[R3b, R4, R5, R6b, R8, R9, R10, R11] — existing behaviour that must stay green.
Fail-closed freshness gate; thresholds evidence-based rather than guessed, or
recorded verbatim as provisional and unmeasured; W1's "deliberately not adopted"
statement replaced in the same commit that activates freshness.
**Depends on:** Phase 2
**Plans:** 4 plans in 4 waves

Plans:

- [x] 03-01-PLAN.md — Arrival signal: `loaded_at` migration and bootstrap replay (wave 1) (completed 2026-08-17)
- [x] 03-02-PLAN.md — Activate freshness: dbt source config, the Airflow gate, and the W1/W2 rewrite (wave 2) (completed 2026-08-17)
- [x] 03-03-PLAN.md — Live proof in CI: fresh passes, stale fails closed, one batch one timestamp (wave 3) (written 2026-08-17; executes on next CI run)
- [x] 03-04-PLAN.md — Live phase gate: DagBag mapping, BDD fail-closed scenario (wave 4) (completed read-only 2026-08-17; threshold measurement declined)

**Wave order is sequential by design.** The operator requires small commits with
verification after each meaningful step, and each wave depends on the previous
one: the column must exist before freshness can be declared, freshness must be
declared before CI can prove it, and the DAG task must exist before the live
DagBag can be observed. There is no parallelism to recover here.

### Phase 4: Medallion Telemetry and Redundant Work Elimination

**Goal:** Make medallion execution telemetry trustworthy, then use that evidence to
eliminate redundant full-state work on unchanged Iceberg state — while preserving
every existing B2, shadow-comparison, recovery, FF-14, Gold and rollout guarantee.

**Why now.** `marts.lakehouse_metrics` records nested `run_b2` and outer `_run_m4`
executions under the same `source`/`status` identity, and the outer
`silver_duration_ms` already contains the nested B2 duration. Historical rows can
therefore be read as separate cycles and B2 time can be double-counted — a defect
that already misled one investigation. Separately, the shadow path performs a full
Bronze scan plus legacy Silver projection plus business-state comparison on every
cycle while `SHADOW_COMPARE=1`, and Gold is overwritten even when persisted Silver
has not moved.

**Explicitly out of scope:** Rust, or any new language or toolchain. No Rust rewrite
is justified by current evidence; the Bronze writer question is unmeasured, not
rejected, and may be reopened on its own measurements later.

**Sequence:** P0 telemetry semantics → P1 shadow fast path (receipt-based) and Gold
provenance → P2 steady-state shadow policy → P3 Arrow/Python profiling, only if still
measurable.

**Requirements**: [MTL-01 cycle_id and phase separation, MTL-02 documented historical
interpretation rule, SHD-01 receipt-based shadow fast path, GLD-01 Gold source
provenance, POL-01 steady-state shadow policy, PRF-01 Arrow boundary profiling,
BENCH-01 before/after measurement]. `TEL-01` renamed to `MTL-01`: TEL-01 is an
already-Complete Phase-1 requirement.
**Depends on:** Phase 3
**Plans:** 10 plans in 8 waves

Plans:

- [x] 04-01-PLAN.md — Wave 0 test infrastructure: phase-named metric accessors, a scripted clock, name-keyed insert assertions, a snapshot-aware Gold double (wave 1)
- [x] 04-02-PLAN.md — Metric identity in the sink: additive cycle/phase schema, cycle-only Prometheus observation, the executable historical rule (wave 2)
- [ ] 04-03-PLAN.md — Cycle identity in the medallion: cycle_id threading, phase records, non-overlapping durations, snapshot ids (wave 3)
- [ ] 04-04-PLAN.md — Cycle-complete stdout marker and marker-based harness liveness, replacing the Gold-snapshot assumption (wave 4)
- [ ] 04-05-PLAN.md — GLD-01 Gold source provenance and no-op rebuild skip, plus the narrow ADR-0001 D-4 amendment (wave 5)
- [ ] 04-06-PLAN.md — SHD-01 durable shadow certificate and the receipt-gated fast path (wave 6)
- [ ] 04-07-PLAN.md — Documentation contract correction and Phase 4 requirement registration (wave 7)
- [ ] 04-08-PLAN.md — POL-01 steady-state shadow policy as ADR-0002; exact rollout-matrix assertion (wave 7)
- [ ] 04-09-PLAN.md — BENCH-01 authorised before/after benchmark on a bounded workload (wave 7, blocking checkpoint)
- [ ] 04-10-PLAN.md — PRF-01 Arrow/Python boundary profile and its optimise-or-not decision (wave 8)

**Wave order is dominated by one file.** Plans 02 through 06 each modify
`iceberg/common/ops.py` or `iceberg/medallion/iceberg_medallion.py` and each depends on
the previous one's API, so there is no parallelism to recover before wave 7. The harness
liveness replacement (04-04) is deliberately scheduled *before* the Gold skip (04-05)
rather than with it: `tests/support/medallion_harness.py` documents "every cycle ends in
a Gold overwrite" as its proof a deployment ran, and `gold_cutover.feature` is a PR
blocker under `ci-m5-gates.yml`. Landing the replacement one wave early means CI
exercises the new signal while it is still equivalent to the old one.
