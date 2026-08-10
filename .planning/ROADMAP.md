# Roadmap: Incremental Lakehouse Demo

## Milestones

- ✓ **Architecture and remediation baseline** — M1–M5, R1/R2, O1, S1, S1.1,
  H1, S1.2A, S1.2A.1, and S1.2B completed and verified at `89953fe`.
- 🚧 **B2 Controlled Rollout** — execute the accepted B2 architecture under
  controlled canary, evidence gate, cutover, and telemetry observation.

## Phases

### Phase 1: B2 Controlled Rollout

**Goal**: Drain legitimate post-migration B2 work safely, prove M5 cutover
conditions, observe real B2 cost, and make an evidence-based D-3a/O2 decision.

**Depends on**: S1.2B verified cleanup at `89953fe`.
**Requirements**: [CAN-01, CAN-02, CAN-03, CUT-01, CUT-02, TEL-01, DEC-01]
**Plans**: 11 plans, including fail-closed runtime gap closure and bounded recovery after the first canary.

**Wave 1**

- [x] 01-01-PLAN.md — Canary preflight and frozen state verification.

**Wave 2** *(executed and failed closed)*

- [x] 01-02-PLAN.md — First controlled B2 canary; restored legacy/legacy/0 after a recovery anomaly.

**Wave 3** *(completed)*

- [x] 01-02A-PLAN.md — Close Iceberg REST catalog concurrency and SQLite lock failures with metadata-preserving PostgreSQL migration.

**Wave 4** *(blocked on 01-02A)*

- [ ] 01-02B-PLAN.md — Reconcile Kafka checkpoint offset loss without resetting history.

**Wave 5** *(blocked on historical 01-02B STOP; stateful execution requires explicit recovery authorization)*

- [ ] 01-02B-R-PLAN.md — Separate bounded Kafka epoch recovery; preserves historical 01-02B STOP and fails closed when completeness or identity cannot be proven.

**Wave 6** *(blocked on 01-02B-R and its post-recovery verification)*

- [ ] 01-02C-PLAN.md — Repeat the guarded B2 canary and require fresh shadow evidence.

**Wave 7** *(blocked on 01-02C)*

- [ ] 01-03-PLAN.md — Drain and verify the 255 legitimate post-migration manifests.

**Wave 8** *(blocked on Wave 7 completion)*

- [ ] 01-04-PLAN.md — Collect and evaluate M5 cutover evidence.

**Wave 9** *(blocked on Wave 8 completion)*

- [ ] 01-05-PLAN.md — Switch Gold to persisted Silver only after a green M5 gate.

**Wave 10** *(blocked on Wave 9 completion)*

- [ ] 01-06-PLAN.md — Collect a representative O1 telemetry window.

**Wave 11** *(blocked on Wave 10 completion)*

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

**Execution Order:** Phase 1 → 01-01 → 01-02 → 01-02A → historical 01-02B STOP → 01-02B-R → 01-02B-V → 01-02C → 01-03 → 01-04 → 01-05 → 01-06 → 01-07

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. B2 Controlled Rollout | Current | 3/11 | In Progress — bounded recovery plan imported; historical 01-02B remains STOP |  |

Historical milestones are intentionally summarized above rather than
replayed as unfinished GSD phases.
